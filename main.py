import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib import request

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from neo4j import GraphDatabase
from pydantic import BaseModel
from pydantic_settings import BaseSettings
from fastapi.responses import FileResponse


load_dotenv(Path(__file__).parent / ".env")


class Settings(BaseSettings):
    NEO4J_URI: str = ""
    NEO4J_USERNAME: str = ""
    NEO4J_PASSWORD: str = ""
    NEO4J_DATABASE: str = ""

    # Optional: if provided, we can use an LLM for natural language answers.
    # MVP can work without it (template-based answer).
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_MODEL: str = "gpt-4o-mini"
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"


def _coerce_node_properties(node_or_props: Any) -> Dict[str, Any]:
    """
    Ensure JSON serializable neo4j node properties.

    Note: Neo4j driver `record.data()` converts Node -> dict of properties,
    so we may receive either a dict or a Neo4j Node object.
    """
    if node_or_props is None:
        return {}
    if isinstance(node_or_props, dict):
        props = node_or_props
    elif hasattr(node_or_props, "_properties"):
        props = getattr(node_or_props, "_properties") or {}
    else:
        try:
            props = dict(node_or_props)
        except Exception:
            return {}

    out: Dict[str, Any] = {}
    for k, v in props.items():
        if isinstance(v, (str, int, float, bool)) or v is None:
            out[k] = v
        else:
            out[k] = str(v)
    return out


class Neo4jClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.driver = GraphDatabase.driver(
            settings.NEO4J_URI,
            auth=(settings.NEO4J_USERNAME, settings.NEO4J_PASSWORD),
        )

    def close(self) -> None:
        self.driver.close()

    def run(self, query: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        params = params or {}
        database = self.settings.NEO4J_DATABASE or None
        with self.driver.session(database=database) as session:
            result = session.run(query, params)
            return [record.data() for record in result]


def _lower(s: str) -> str:
    return (s or "").strip().lower()

def _split_csv_list(s: str) -> List[str]:
    """
    Split a comma-separated input string into a clean list of tokens.
    """
    parts = [p.strip() for p in (s or "").split(",")]
    return [p for p in parts if p]

def _extract_after_keyword(text: str, keyword: str) -> str:
    # e.g. text="类似鲁鲁修的动漫", keyword="类似"
    # e.g. text="Anime like Code Geass", keyword="like"
    idx = text.lower().find(keyword.lower())
    if idx < 0:
        return ""
    tail = text[idx + len(keyword) :]
    # Remove leading symbols/spaces
    tail = re.sub(r"^[\s:：\-?？]+", "", tail)
    # Split by common delimiters
    tail = re.split(r"[?？。.!！\n\r,，、]", tail)[0]
    tail = tail.strip()
    
    # Strip common suffixes/prefixes for better matching
    tail = re.sub(r"(的动漫|的动画|的作品|的漫画|的电影|的剧|这部|那部)$", "", tail).strip()
    # English specific cleanup
    tail = re.sub(r"^(some anime|anime|works|series|shows|movies)\s+(like|similar to)\s+", "", tail, flags=re.I).strip()
    return tail


def _parse_intent(query: str) -> Dict[str, Any]:
    q = (query or "").strip()
    q_lower = q.lower()

    # 1) Similar anime: "类似鲁鲁修的动漫" / "Recommend some anime like Code Geass"
    # Keywords: 类似, 像, 相似, 差不多, like, similar to, resembles
    similar_keywords = ["类似", "像", "相似", "差不多", "like", "similar to", "resembles", "recommend some anime like"]
    for kw in similar_keywords:
        if kw in q_lower:
            target = _extract_after_keyword(q, kw)
            if target:
                return {"intent": "similar_anime", "target": target}

    # 2) Voice Actor / Casting: "谁给鲁鲁修配音的" / "Who is the voice actor for Saber?"
    # Keywords: 配音, 声优, CV, cv, voice actor, voice by, voices, voiced by
    if any(k in q_lower for k in ["配音", "声优", "cv", "voice actor", "voice by", "voices", "voiced by"]):
        # Case A: English patterns
        # "Who is the voice actor for [Saber]?"
        # "Who voices [Saber]?"
        # "Voice actor of [Saber]"
        va_patterns = [
            r"voice actor (for|of|to)\s+(.+)",
            r"voices\s+(.+)",
            r"voiced by\s+(.+)",
            r"cv (for|of)\s+(.+)"
        ]
        for p in va_patterns:
            m = re.search(p, q_lower)
            if m:
                # Group 2 is usually the character name
                char = m.group(m.lastindex).strip()
                char = re.sub(r"[?！.!]+$", "", char).strip()
                if char: return {"intent": "character_casting", "character": char}

        # Case B: Chinese patterns
        m_cn = re.search(r"谁给(.+?)配音", q)
        if m_cn:
            return {"intent": "character_casting", "character": m_cn.group(1).strip()}
        
        # Case C: "有哪些声优擅长[标签]"
        tag_match = re.search(r"擅长(.+?)(的声优|的CV|的cv)", q)
        if tag_match:
            return {"intent": "casting_by_tags", "tags": [tag_match.group(1).strip()]}

    # 3) Studio: "BONES制作的动漫" / "Anime produced by Madhouse"
    if any(k in q_lower for k in ["制作公司", "出品", "公司", "制作", "produced by", "studio", "made by"]):
        # English patterns
        studio_patterns = [
            r"produced by\s+(.+)",
            r"made by\s+(.+)",
            r"studio\s+(.+)"
        ]
        for p in studio_patterns:
            m = re.search(p, q_lower)
            if m:
                studio = m.group(1).strip()
                studio = re.sub(r"[?！.!]+$", "", studio).strip()
                if studio: return {"intent": "studio_works", "studio": studio}

        # Chinese patterns
        m_cn = re.search(r"(.+?)(制作|出品|公司)", q)
        if m_cn:
            studio = m_cn.group(1).strip()
            if studio and len(studio) < 15 and studio not in ["有哪些", "推荐", "什么"]:
                return {"intent": "studio_works", "studio": studio}

    # 4) Tag intersection: "哪些动漫是智斗+政治" / "Battle and Magic anime"
    tag_tokens = []
    # Common separators
    separators = ["和", "+", "、", ",", "，", "以及", " and ", " & "]
    if any(sep in q_lower for sep in separators):
        possible = q
        # Remove common prefixes
        possible = re.sub(r"^(哪些动漫|哪些|推荐|相似|有什么|有哪些|推荐几部|给我找找|recommend|show me|find|search for|some)\s+", "", possible, flags=re.I).strip()
        # Remove common verbs
        possible = re.sub(r"(是|属于|包含|有|带|拥有|关于|with|that have|featuring|are|is)\s+", "", possible, flags=re.I).strip()
        
        # Normalize separators to " and "
        norm = possible
        for sep in ["和", "+", "、", ",", "，", "以及", "&"]:
            norm = norm.replace(sep, " and ")
        
        parts = re.split(r"\s+and\s+", norm, flags=re.I)
        parts = [p.strip() for p in parts if p.strip()]
        for p in parts[:6]:
            if 1 <= len(p) <= 15:
                tag_tokens.append(p)
        if len(tag_tokens) >= 2:
            return {"intent": "tag_intersection", "tags": tag_tokens}

    # 5) Character appearance: "某角色出现在哪" / "Where does Saber appear?"
    if any(k in q_lower for k in ["出现", "登场", "在哪", "出演", "appear", "where is", "show up"]):
        # English patterns
        char_patterns = [
            r"where (does|is)\s+(.+?)\s+(appear|show up)",
            r"where is\s+(.+?)",
            r"(.+?)\s+appears in"
        ]
        for p in char_patterns:
            m = re.search(p, q_lower)
            if m:
                character = m.group(m.lastindex-1 if "appear" in p else m.lastindex).strip()
                character = re.sub(r"[?！.!]+$", "", character).strip()
                if character: return {"intent": "character_appears", "character": character}

        # Chinese patterns
        m_cn = re.search(r"(.+?)(出现|登场|出演|在哪里|在哪)", q)
        if m_cn:
            character = m_cn.group(1).strip()
            if character and character not in ["有哪些", "推荐", "什么"]:
                return {"intent": "character_appears", "character": character}

    # 6) Direct search
    return {"intent": "search", "q": q}


class ChatRequest(BaseModel):
    query: str


class GraphQueryParams(BaseModel):
    name: str
    depth: int = 1


class ChatResponse(BaseModel):
    answer: str
    recommendations: List[Dict[str, Any]]
    graph_paths: List[Dict[str, Any]]
    keywords: List[str] = []


def _cypher_for_subgraph(name: str, depth: int) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    # Keep this conservative so the graph won't blow up on large datasets.
    # Returned format:
    # nodes: [{"id","label","type","properties"}]
    # edges: [{"id","source","target","type","label"}]
    # We will build graph in python using multiple small queries.
    return [], []


def build_graph_subgraph(client: Neo4jClient, name: str, depth: int = 1) -> Dict[str, Any]:
    # MVP graph: central Anime + immediate neighbors, plus second level tags for similar anime when depth>=2.
    # Assumptions (can be adapted later after confirming your schema):
    # - Nodes have property `name`
    # - Labels: Anime/Character/Tag/Theme/Studio
    # - Relationships: HAS_TAG, HAS_CHARACTER, SIMILAR_TO, APPEARS_IN/RELATED
    #
    # We try multiple relationship directions to be robust.
    depth = max(1, min(int(depth or 1), 3))

    def add_node(nodes: Dict[str, Dict[str, Any]], node_id: str, label: str, ntype: str, props: Optional[Dict[str, Any]] = None):
        if node_id not in nodes:
            nodes[node_id] = {
                "id": node_id,
                "label": label,
                "type": ntype,
                "properties": props or {},
            }

    nodes: Dict[str, Dict[str, Any]] = {}
    edges: List[Dict[str, Any]] = []
    edge_set = set()

    def add_edge(source: str, target: str, rtype: str, label: Optional[str] = None):
        eid = f"{source}|{target}|{rtype}|{label or ''}"
        if eid in edge_set:
            return
        edge_set.add(eid)
        edges.append(
            {
                "id": eid,
                "source": source,
                "target": target,
                "type": rtype,
                "label": label or rtype,
            }
        )

    # Central anime
    def resolve_anime_display_name(raw: str) -> Optional[str]:
        # Prefer exact match on coalesce(name_cn,name); then fall back to contains match.
        exact = """
        MATCH (a:Anime)
        WHERE toLower(coalesce(a.name_cn, a.name)) = toLower($name)
        RETURN coalesce(a.name_cn, a.name) as display
        LIMIT 1
        """
        rows = client.run(exact, {"name": raw})
        if rows:
            return rows[0]["display"]
        contains = """
        MATCH (a:Anime)
        WHERE toLower(coalesce(a.name_cn, a.name)) CONTAINS toLower($name)
        RETURN coalesce(a.name_cn, a.name) as display
        LIMIT 1
        """
        rows = client.run(contains, {"name": raw})
        if rows:
            return rows[0]["display"]
        return None

    anime_q = """
    MATCH (a:Anime)
    WHERE toLower(coalesce(a.name_cn, a.name)) = toLower($name)
    RETURN a
    LIMIT 1
    """
    rows = client.run(anime_q, {"name": name})
    if not rows:
        # Try contains match for nicer UX
        anime_q2 = """
        MATCH (a:Anime)
        WHERE toLower(coalesce(a.name_cn, a.name)) CONTAINS toLower($name)
        RETURN a
        LIMIT 1
        """
        rows = client.run(anime_q2, {"name": name})
    if not rows:
        return {"nodes": [], "edges": [], "centerFound": False}

    a_node = rows[0]["a"]
    a_props = _coerce_node_properties(a_node)
    a_name = a_props.get("name_cn") or a_props.get("name") or name
    center_id = f"Anime::{a_name}"
    add_node(nodes, center_id, a_name, "Anime", a_props)

    # Tags
    tag_rows = client.run(
        """
        MATCH (a:Anime)-[r:HAS_TAG]->(t:Tag)
        WHERE toLower(coalesce(a.name_cn, a.name)) = toLower($name)
        RETURN t, type(r) as rel_type
        """,
        {"name": a_name},
    )
    for r in tag_rows:
        t = r["t"]
        t_props = _coerce_node_properties(t)
        t_name = t_props.get("name") or str(t)
        t_id = f"Tag::{t_name}"
        add_node(nodes, t_id, t_name, "Tag", t_props)
        add_edge(center_id, t_id, "HAS_TAG")

    # Characters
    char_rows = client.run(
        """
        MATCH (a:Anime)-[r:HAS_CHARACTER]->(c:Character)
        WHERE toLower(coalesce(a.name_cn, a.name)) = toLower($name)
        RETURN c
        """,
        {"name": a_name},
    )
    for r in char_rows:
        c = r["c"]
        c_props = _coerce_node_properties(c)
        c_name = c_props.get("name") or str(c)
        c_id = f"Character::{c_name}"
        add_node(nodes, c_id, c_name, "Character", c_props)
        add_edge(center_id, c_id, "HAS_CHARACTER")

    # Similar anime
    similar_rows = client.run(
        """
        MATCH (a:Anime)-[r:SIMILAR_TO]->(b:Anime)
        WHERE toLower(coalesce(a.name_cn, a.name)) = toLower($name)
        RETURN b
        LIMIT 30
        """,
        {"name": a_name},
    )
    similar_names: List[str] = []
    for r in similar_rows:
        b = r["b"]
        b_props = _coerce_node_properties(b)
        b_name = b_props.get("name_cn") or b_props.get("name") or str(b)
        similar_names.append(b_name)
        b_id = f"Anime::{b_name}"
        add_node(nodes, b_id, b_name, "Anime", b_props)
        add_edge(center_id, b_id, "SIMILAR_TO")

    # Depth>=2: add tags for similar anime (so graph looks richer)
    if depth >= 2 and similar_names:
        for b_name in similar_names[:20]:
            tag_rows_2 = client.run(
                """
                MATCH (b:Anime)-[:HAS_TAG]->(t:Tag)
                WHERE toLower(coalesce(b.name_cn, b.name)) = toLower($name)
                RETURN t
                LIMIT 15
                """,
                {"name": b_name},
            )
            b_id = f"Anime::{b_name}"
            for r in tag_rows_2:
                t = r["t"]
                t_props = _coerce_node_properties(t)
                t_name = t_props.get("name") or str(t)
                t_id = f"Tag::{t_name}"
                add_node(nodes, t_id, t_name, "Tag", t_props)
                add_edge(b_id, t_id, "HAS_TAG")

    return {
        "nodes": list(nodes.values()),
        "edges": edges,
        "centerFound": True,
        "centerName": a_name,
    }


def recommend_similar_anime(client: Neo4jClient, target: str, limit: int = 10) -> Dict[str, Any]:
    # Recommend by shared tags.
    # Resolve input to a display title from Neo4j to reduce “no match” cases.
    resolve = """
    MATCH (a:Anime)
    WHERE toLower(coalesce(a.name_cn, a.name)) = toLower($raw)
    RETURN coalesce(a.name_cn, a.name) as display
    LIMIT 1
    """
    rows = client.run(resolve, {"raw": target})
    target_display = rows[0]["display"] if rows else ""
    if not target_display:
        resolve2 = """
        MATCH (a:Anime)
        WHERE toLower(coalesce(a.name_cn, a.name)) CONTAINS toLower($raw)
        RETURN coalesce(a.name_cn, a.name) as display
        LIMIT 1
        """
        rows2 = client.run(resolve2, {"raw": target})
        target_display = rows2[0]["display"] if rows2 else target

    print(f">>> [SIMILAR RECOMMEND] Target resolved to: '{target_display}'")

    cypher = """
    MATCH (a:Anime)-[:HAS_TAG]->(t:Tag)<-[:HAS_TAG]-(b:Anime)
    WHERE toLower(coalesce(a.name_cn, a.name)) CONTAINS toLower($target)
      AND toLower(coalesce(b.name_cn, b.name)) <> toLower(coalesce(a.name_cn, a.name))
    RETURN coalesce(b.name_cn, b.name) as anime, count(t) as score,
           collect(distinct t.name) as matched_tags
    ORDER BY score DESC
    LIMIT $limit
    """
    rows = client.run(cypher, {"target": target_display, "limit": int(limit)})
    recommendations: List[Dict[str, Any]] = []
    for r in rows:
        recommendations.append(
            {
                "name": r["anime"],
                "score": int(r["score"]) if r["score"] is not None else 0,
                "matchedTags": r.get("matched_tags") or [],
            }
        )

    # Build paths for top 3 recommendations (central -> shared tags -> rec)
    graph_paths: List[Dict[str, Any]] = []
    for rec in recommendations[:3]:
        shared_tags = rec["matchedTags"][:8]
        # edges for visualization
        path = {
            "source": target_display,
            "target": rec["name"],
            "viaTags": shared_tags,
            "edges": [],
        }
        for tag in shared_tags:
            path["edges"].append({"source": f"Anime::{target_display}", "target": f"Tag::{tag}", "type": "HAS_TAG"})
            path["edges"].append({"source": f"Tag::{tag}", "target": f"Anime::{rec['name']}", "type": "HAS_TAG"})
        graph_paths.append(path)

    # Template answer (no LLM required)
    if recommendations:
        top = recommendations[0]
        answer = f"The anime sharing the most tags with <{target_display}> is <{top['name']}> ({top['score']} shared tags). You might also like: "
        names = [x["name"] for x in recommendations[:5]]
        answer += ", ".join([f"<{n}>" for n in names])
    else:
        answer = f"No similar anime found in the graph for <{target_display}>. Try a more specific title."

    return {"answer": answer, "recommendations": recommendations, "graph_paths": graph_paths}


def recommend_by_tags(client: Neo4jClient, tags: List[str], limit: int = 10) -> Dict[str, Any]:
    # Intersection by counting matched tags.
    tags = [t for t in tags if t]
    if not tags:
        return {"answer": "No valid tags found.", "recommendations": [], "graph_paths": []}

    # Tag fuzzy matching: find actual tag names from database
    resolved_tags = []
    for t in tags:
        res = client.run("""
            MATCH (tag:Tag)
            WHERE toLower(tag.name) CONTAINS toLower($t)
            RETURN tag.name as name
            ORDER BY size(tag.name) ASC
            LIMIT 1
        """, {"t": t})
        if res:
            resolved_tags.append(res[0]["name"])
        else:
            # If no match, keep original and let Neo4j try
            resolved_tags.append(t)

    cypher = """
    MATCH (a:Anime)-[:HAS_TAG]->(t:Tag)
    WHERE toLower(t.name) IN $tag_names
    WITH a, collect(distinct toLower(t.name)) as matched
    // Return animes matching any of the tags, but sort by match count
    WITH a, matched, size(matched) as score
    MATCH (a)-[:HAS_TAG]->(t:Tag)
    WHERE toLower(t.name) IN $tag_names
    WITH a, score, collect(distinct t.name) as matched_tags
    ORDER BY score DESC
    LIMIT $limit
    RETURN coalesce(a.name_cn, a.name) as anime, score, matched_tags
    """
    tag_names = [t.lower() for t in resolved_tags]
    rows = client.run(cypher, {"tag_names": tag_names, "limit": int(limit)})
    recommendations: List[Dict[str, Any]] = []
    for r in rows:
        recommendations.append(
            {
                "name": r["anime"],
                "score": int(r["score"]) if r["score"] is not None else 0,
                "matchedTags": r.get("matched_tags") or [],
            }
        )

    # Path: for top 3 recs, show shared tags between the tag set and the anime.
    graph_paths: List[Dict[str, Any]] = []
    for rec in recommendations[:3]:
        viaTags = (rec["matchedTags"] or [])[:8]
        graph_paths.append(
            {
                "source": "TAGS",
                "target": rec["name"],
                "viaTags": viaTags,
                "edges": [{"source": f"Tag::{t}", "target": f"Anime::{rec['name']}", "type": "HAS_TAG"} for t in viaTags],
            }
        )

    answer = f"I found anime matching these tags: {', '.join(resolved_tags)}."
    if recommendations:
        answer += f" Top matches include <{recommendations[0]['name']}>."
    else:
        answer += " No exact matches found in the graph for these tags."
    return {"answer": answer, "recommendations": recommendations, "graph_paths": graph_paths}


def search_anime(client: Neo4jClient, q: str, limit: int = 10) -> List[Dict[str, Any]]:
    q = (q or "").strip()
    if not q:
        return []
    # 1) Direct name contains
    cypher_1 = """
    MATCH (a:Anime)
    WHERE toLower(coalesce(a.name_cn, a.name)) CONTAINS toLower($q)
    RETURN coalesce(a.name_cn, a.name) as anime, 100 as score
    LIMIT $limit
    """
    rows = client.run(cypher_1, {"q": q, "limit": int(limit)})
    out: Dict[str, Dict[str, Any]] = {r["anime"]: {"name": r["anime"], "score": int(r["score"] or 0), "matchedTags": []} for r in rows}

    # 2) Tag contains -> return animes
    cypher_2 = """
    MATCH (a:Anime)-[:HAS_TAG]->(t:Tag)
    WHERE toLower(t.name) CONTAINS toLower($q)
    RETURN coalesce(a.name_cn, a.name) as anime, count(distinct t) as score, collect(distinct t.name) as matched_tags
    ORDER BY score DESC
    LIMIT $limit
    """
    rows2 = client.run(cypher_2, {"q": q, "limit": int(limit)})
    for r in rows2:
        name = r["anime"]
        score = int(r["score"] or 0)
        if name in out:
            out[name]["score"] = max(out[name]["score"], score)
            # Merge matchedTags
            out[name]["matchedTags"] = list(set(out[name]["matchedTags"] + (r.get("matched_tags") or [])))
        else:
            out[name] = {"name": name, "score": score, "matchedTags": r.get("matched_tags") or []}

    return sorted(out.values(), key=lambda x: x["score"], reverse=True)[: int(limit)]


def get_anime_detail(client: Neo4jClient, name: str) -> Dict[str, Any]:
    cypher = """
    MATCH (a:Anime)
    WHERE toLower(coalesce(a.name_cn, a.name)) = toLower($name)
    RETURN a
    LIMIT 1
    """
    rows = client.run(cypher, {"name": name})
    if not rows:
        cypher2 = """
        MATCH (a:Anime)
        WHERE toLower(coalesce(a.name_cn, a.name)) CONTAINS toLower($name)
        RETURN a
        LIMIT 1
        """
        rows = client.run(cypher2, {"name": name})
    if not rows:
        return {"found": False}
    a = rows[0]["a"]
    props = _coerce_node_properties(a)
    anime_name = props.get("name_cn") or props.get("name") or name

    tags = client.run(
        """
        MATCH (a:Anime)-[:HAS_TAG]->(t:Tag)
        WHERE toLower(coalesce(a.name_cn, a.name)) = toLower($name)
        RETURN t.name as tag
        LIMIT 50
        """,
        {"name": anime_name},
    )
    characters = client.run(
        """
        MATCH (a:Anime)-[:HAS_CHARACTER]->(c:Character)
        WHERE toLower(coalesce(a.name_cn, a.name)) = toLower($name)
        RETURN c.name as character
        LIMIT 50
        """,
        {"name": anime_name},
    )
    similar = client.run(
        """
        MATCH (a:Anime)-[:SIMILAR_TO]->(b:Anime)
        WHERE toLower(coalesce(a.name_cn, a.name)) = toLower($name)
        RETURN coalesce(b.name_cn, b.name) as anime
        LIMIT 20
        """,
        {"name": anime_name},
    )

    return {
        "found": True,
        "anime": props,
        "tags": [r["tag"] for r in tags],
        "characters": [r["character"] for r in characters],
        "similar": [r["anime"] for r in similar],
    }


def create_app() -> FastAPI:
    settings = Settings()
    print(f"--- Settings Loaded ---")
    print(f"Neo4j URI: {settings.NEO4J_URI}")
    print(f"OpenAI Key Configured: {'Yes' if settings.OPENAI_API_KEY else 'No'}")
    print(f"-----------------------")
    
    client: Optional[Neo4jClient] = None
    if settings.NEO4J_URI and settings.NEO4J_USERNAME and settings.NEO4J_PASSWORD:
        client = Neo4jClient(settings)

    app = FastAPI(title="Anime Graph Explorer", version="0.1.0")
    app.state.neo4j = client

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Static frontend (single-page)
    static_dir = Path(__file__).parent / "static"
    app.mount("/static", StaticFiles(directory=str(static_dir), html=False), name="static")

    @app.get("/")
    def index():
        print(">>> [CRITICAL] User hit the homepage route!", flush=True)
        return FileResponse(str(static_dir / "index_en.html"))

    @app.get("/en")
    def index_en():
        return FileResponse(str(static_dir / "index_en.html"))

    def require_client():
        if client is None:
            # Make it friendly for first-time setup.
            return None
        return client

    def _llm_generate_answer(question: str, graph_payload: ChatResponse) -> Tuple[Optional[str], List[str]]:
        # If user hasn't configured any LLM key, fall back to template answer.
        if not settings.OPENAI_API_KEY:
            print("!! LLM Skipped: OPENAI_API_KEY not found in settings.")
            return None, []

        graph_paths = graph_payload.graph_paths or []
        recs = graph_payload.recommendations or []

        def compact_paths(paths: List[Dict[str, Any]], max_items: int = 3) -> List[Dict[str, Any]]:
            out: List[Dict[str, Any]] = []
            for p in (paths or [])[:max_items]:
                out.append(
                    {
                        "source": p.get("source"),
                        "target": p.get("target"),
                        "viaTags": (p.get("viaTags") or [])[:10],
                    }
                )
            return out

        context = {
            "question": question,
            "topRecommendations": [
                {"name": r.get("name"), "score": r.get("score"), "matchedTags": (r.get("matchedTags") or [])[:10]}
                for r in recs[:8]
            ],
            "graphPaths": compact_paths(graph_paths, max_items=3),
        }

        system = (
            "You are an expert anime recommendation assistant powered by a Neo4j knowledge graph. "
            "STRICT REQUIREMENT: YOUR ENTIRE RESPONSE MUST BE IN ENGLISH. "
            "Provide natural language explanations based on the provided graphPaths and topRecommendations. "
            "If the recommendations involve shared tags, explain why those tags are relevant to the user's interests. "
            "If the recommendation involves a specific character, voice actor, or studio, highlight that connection. "
            "Be conversational, enthusiastic, and helpful. Use anime-related terminology correctly."
        )
        user = (
            "Explain the following graph-based recommendation reasoning in a natural, helpful way. "
            "CRITICAL: DO NOT USE CHINESE. RESPOND ONLY IN ENGLISH.\n\n"
            f"User Question: {question}\n\n"
            f"Graph Reasoning Context (JSON): {json.dumps(context, ensure_ascii=False)}\n\n"
            "Output Requirements:\n"
            "1) Start with a direct answer or conclusion in English.\n"
            "2) Use 2-4 bullet points to explain the 'why' (e.g., shared tags like 'Battle' or 'Sci-Fi', same studio, or same voice actor).\n"
            "3) If there are graph paths, mention how the nodes are connected.\n"
            "4) End with a warm, actionable suggestion.\n"
            "5) IMPORTANT: After your response, add a section labeled 'KEYWORDS:' followed by 3-5 short comma-separated key phrases summarizing the answer (e.g., KEYWORDS: Psychological, Mind Games, Strategy, Sci-Fi).\n"
        )

        url = f"{settings.OPENAI_BASE_URL}/chat/completions"
        headers = {
            "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
            "Content-Type": "application/json",
        }
        base_body = {
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": 0.4,
            "max_tokens": 400,
        }

        # Try the configured model first; if it fails due to model issues, fall back.
        models_to_try: List[str] = []
        if settings.OPENAI_MODEL:
            models_to_try.append(settings.OPENAI_MODEL)
        if "gpt-4o-mini" not in models_to_try:
            models_to_try.append("gpt-4o-mini")

        print(f">> LLM Request: Sending to OpenAI (model: {settings.OPENAI_MODEL})...")
        for model_name in models_to_try:
            try:
                body = dict(base_body)
                body["model"] = model_name
                req = request.Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
                with request.urlopen(req, timeout=60) as resp:
                    resp_body = json.loads(resp.read().decode("utf-8"))
                content = resp_body["choices"][0]["message"]["content"]
                
                # Split content and keywords
                answer_part = content
                keywords_part = []
                if "KEYWORDS:" in content:
                    parts = content.split("KEYWORDS:")
                    answer_part = parts[0].strip()
                    kw_str = parts[1].strip()
                    keywords_part = [k.strip() for k in kw_str.split(",") if k.strip()]

                print(f">> LLM Success: Received response from {model_name} (length: {len(content)})")
                return answer_part, keywords_part
            except Exception as e:
                msg = str(e)
                print(f"!! LLM Error (model={model_name}): {repr(e)}")
                # Unauthorized/Forbidden won't be solved by changing model.
                if "401" in msg or "403" in msg or "Unauthorized" in msg or "Forbidden" in msg:
                    print("!! Critical LLM Auth Error. Check API Key.")
                    return None, []

                # Otherwise, keep trying the next model.
                continue

        return None, []

    @app.get("/api/graph")
    def api_graph(name: str, depth: int = 1):
        c = require_client()
        if c is None:
            return {"nodes": [], "edges": [], "centerFound": False, "error": "Neo4j 未配置：请先在 backend/.env 填写 NEO4J_URI/NEO4J_USERNAME/NEO4J_PASSWORD。" }
        return build_graph_subgraph(c, name=name, depth=depth)

    @app.get("/api/expand")
    def api_expand(label: str, type: str):
        c = require_client()
        if c is None:
            return {"nodes": [], "edges": []}

        # Expansion logic for any node type
        nodes: Dict[str, Dict[str, Any]] = {}
        edges: List[Dict[str, Any]] = []
        edge_set = set()

        def add_node(node_id: str, label: str, ntype: str, props: Optional[Dict[str, Any]] = None):
            if node_id not in nodes:
                nodes[node_id] = {
                    "id": node_id,
                    "label": label,
                    "type": ntype,
                    "properties": props or {},
                }

        def add_edge(source: str, target: str, rtype: str):
            eid = f"{source}|{target}|{rtype}"
            if eid in edge_set: return
            edge_set.add(eid)
            edges.append({"id": eid, "source": source, "target": target, "type": rtype, "label": rtype})

        # Security: whitelist allowed labels for dynamic cypher
        allowed_labels = {"Anime", "Character", "Tag", "Studio", "VoiceActor", "Country"}
        if type not in allowed_labels:
            return {"nodes": [], "edges": []}

        # Query neighbors
        # For Anime, we use coalesce(name_cn, name)
        name_filter = "coalesce(n.name_cn, n.name) = $label" if type == "Anime" else "n.name = $label"
        cypher = f"""
        MATCH (n:`{type}`) WHERE {name_filter}
        MATCH (n)-[r]-(m)
        RETURN n, m, type(r) as rel_type, labels(m)[0] as m_type, 
               startNode(r) = n as is_outgoing
        LIMIT 40
        """
        
        rows = c.run(cypher, {"label": label})
        for r in rows:
            n_node = r["n"]
            m_node = r["m"]
            m_type = r["m_type"]
            rel_type = r["rel_type"]
            is_outgoing = r["is_outgoing"]

            n_props = _coerce_node_properties(n_node)
            m_props = _coerce_node_properties(m_node)

            n_display = n_props.get("name_cn") or n_props.get("name") or label
            m_display = m_props.get("name_cn") or m_props.get("name") or str(m_node)

            n_id = f"{type}::{n_display}"
            m_id = f"{m_type}::{m_display}"

            add_node(n_id, n_display, type, n_props)
            add_node(m_id, m_display, m_type, m_props)

            if is_outgoing:
                add_edge(n_id, m_id, rel_type)
            else:
                add_edge(m_id, n_id, rel_type)

        return {"nodes": list(nodes.values()), "edges": edges}

    @app.get("/api/search")
    def api_search(query: Optional[str] = None, q: Optional[str] = None, limit: int = 10):
        c = require_client()
        if c is None:
            return {"results": [], "error": "Neo4j 未配置：请先在 backend/.env 填写 Neo4j 连接信息。"}
        q_in = query if query is not None else q
        if not q_in:
            return {"results": [], "error": None}
        return {"results": search_anime(c, q=q_in, limit=limit)}

    @app.get("/api/recommend")
    def api_recommend(id: str, limit: int = 10):
        c = require_client()
        if c is None:
            return {"recommendations": [], "graph_paths": [], "error": "Neo4j 未配置"}

        resolve = """
        MATCH (a:Anime)
        WHERE toString(a.id) = toString($id)
        RETURN coalesce(a.name_cn, a.name) as display
        LIMIT 1
        """
        rows = c.run(resolve, {"id": id})
        if not rows:
            return {"recommendations": [], "graph_paths": [], "error": f"Anime ID not found: {id}"}
        display = rows[0]["display"]
        return recommend_similar_anime(c, target=display, limit=limit)

    @app.get("/api/casting")
    def api_casting(tags: str, limit: int = 10):
        c = require_client()
        if c is None:
            return {"voiceActors": [], "nodes": [], "edges": [], "error": "Neo4j 未配置"}

        tag_tokens = _split_csv_list(tags)
        if not tag_tokens:
            return {"voiceActors": [], "nodes": [], "edges": [], "error": "No valid tags provided."}

        # Expansion logic for casting
        nodes: Dict[str, Dict[str, Any]] = {}
        edges: List[Dict[str, Any]] = []
        edge_set = set()

        def add_node(node_id: str, label: str, ntype: str, props: Optional[Dict[str, Any]] = None):
            if node_id not in nodes:
                nodes[node_id] = {"id": node_id, "label": label, "type": ntype, "properties": props or {}}

        def add_edge(source: str, target: str, rtype: str):
            eid = f"{source}|{target}|{rtype}"
            if eid in edge_set: return
            edge_set.add(eid)
            edges.append({"id": eid, "source": source, "target": target, "type": rtype, "label": rtype})

        # Check if any token matches a Tag in the database; if so, use tag-based search
        tag_names = [t.lower() for t in tag_tokens]
        tag_check = c.run("""
            MATCH (t:Tag)
            WHERE toLower(t.name) IN $tag_names
            RETURN count(t) as cnt
        """, {"tag_names": tag_names})
        is_tag_search = tag_check and tag_check[0].get("cnt", 0) > 0

        if not is_tag_search and len(tag_tokens) == 1:
            # Treat single token as VA name search
            va_name = tag_tokens[0]
            va_search = """
            MATCH (v:VoiceActor)
            WHERE toLower(v.name) CONTAINS toLower($name)
            OPTIONAL MATCH (v)<-[:VOICED_BY]-(ch:Character)<-[:HAS_CHARACTER]-(a:Anime)
            RETURN v, ch, a
            LIMIT $limit
            """
            rows = c.run(va_search, {"name": va_name, "limit": int(limit)})
            va_list = []
            va_added = set()
            for r in rows:
                v_node = r["v"]
                v_props = _coerce_node_properties(v_node)
                v_name = v_props.get("name")
                v_id = f"VoiceActor::{v_name}"
                add_node(v_id, v_name, "VoiceActor", v_props)
                if v_name not in va_added:
                    va_list.append({"name": v_name, "score": 100})
                    va_added.add(v_name)
                
                if r["ch"] and r["a"]:
                    ch_props = _coerce_node_properties(r["ch"])
                    a_props = _coerce_node_properties(r["a"])
                    ch_name = ch_props.get("name")
                    a_name = a_props.get("name_cn") or a_props.get("name")
                    ch_id = f"Character::{ch_name}"
                    a_id = f"Anime::{a_name}"
                    add_node(ch_id, ch_name, "Character", ch_props)
                    add_node(a_id, a_name, "Anime", a_props)
                    add_edge(ch_id, v_id, "VOICED_BY")
                    add_edge(a_id, ch_id, "HAS_CHARACTER")
            
            return {"voiceActors": va_list, "nodes": list(nodes.values()), "edges": edges}

        # Tag-based casting search: find voice actors in anime matching the given tags
        cypher = """
        MATCH (a:Anime)-[:HAS_TAG]->(t:Tag)
        WHERE toLower(t.name) IN $tag_names
        WITH a, collect(distinct toLower(t.name)) as matchedLower, count(distinct t) as matchCount
        MATCH (a)-[:HAS_CHARACTER]->(ch:Character)-[:VOICED_BY]->(v:VoiceActor)
        RETURN v, ch, a, matchCount
        ORDER BY matchCount DESC
        LIMIT $limit
        """
        rows = c.run(cypher, {"tag_names": tag_names, "limit": int(limit)})
        va_map = {}
        for r in rows:
            v_node = r["v"]
            ch_node = r["ch"]
            a_node = r["a"]
            
            v_props = _coerce_node_properties(v_node)
            ch_props = _coerce_node_properties(ch_node)
            a_props = _coerce_node_properties(a_node)
            
            v_name = v_props.get("name")
            ch_name = ch_props.get("name")
            a_name = a_props.get("name_cn") or a_props.get("name")
            
            v_id = f"VoiceActor::{v_name}"
            ch_id = f"Character::{ch_name}"
            a_id = f"Anime::{a_name}"
            
            add_node(v_id, v_name, "VoiceActor", v_props)
            add_node(ch_id, ch_name, "Character", ch_props)
            add_node(a_id, a_name, "Anime", a_props)
            add_edge(ch_id, v_id, "VOICED_BY")
            add_edge(a_id, ch_id, "HAS_CHARACTER")
            
            va_map[v_name] = va_map.get(v_name, 0) + 1
            
        va_list = [{"name": name, "score": score} for name, score in sorted(va_map.items(), key=lambda x: x[1], reverse=True)]
        return {"voiceActors": va_list, "nodes": list(nodes.values()), "edges": edges}

    @app.get("/api/character")
    def api_character(name: str, limit: int = 20):
        c = require_client()
        if c is None:
            return {"animes": [], "nodes": [], "edges": [], "error": "Neo4j 未配置"}

        resolve_exact = """
        MATCH (ch:Character)
        WHERE toLower(ch.name) = toLower($raw)
        RETURN ch.name as display
        LIMIT 1
        """
        rows = c.run(resolve_exact, {"raw": name})
        display = rows[0]["display"] if rows else ""
        if not display:
            resolve_contains = """
            MATCH (ch:Character)
            WHERE toLower(ch.name) CONTAINS toLower($raw)
            RETURN ch.name as display
            LIMIT 1
            """
            rows2 = c.run(resolve_contains, {"raw": name})
            display = rows2[0]["display"] if rows2 else name

        nodes: Dict[str, Dict[str, Any]] = {}
        edges: List[Dict[str, Any]] = []
        edge_set = set()

        def add_node(node_id: str, label: str, ntype: str, props: Optional[Dict[str, Any]] = None):
            if node_id not in nodes:
                nodes[node_id] = {"id": node_id, "label": label, "type": ntype, "properties": props or {}}

        def add_edge(source: str, target: str, rtype: str):
            eid = f"{source}|{target}|{rtype}"
            if eid in edge_set: return
            edge_set.add(eid)
            edges.append({"id": eid, "source": source, "target": target, "type": rtype, "label": rtype})

        cypher = """
        MATCH (a:Anime)-[:HAS_CHARACTER]->(ch:Character)
        WHERE toLower(ch.name) = toLower($cname)
        RETURN a, ch
        ORDER BY a.score DESC
        LIMIT $limit
        """
        rows = c.run(cypher, {"cname": display, "limit": int(limit)})
        animes = []
        for r in rows:
            a_node = r["a"]
            ch_node = r["ch"]
            a_props = _coerce_node_properties(a_node)
            ch_props = _coerce_node_properties(ch_node)
            a_name = a_props.get("name_cn") or a_props.get("name")
            ch_name = ch_props.get("name")
            a_id = f"Anime::{a_name}"
            ch_id = f"Character::{ch_name}"
            add_node(a_id, a_name, "Anime", a_props)
            add_node(ch_id, ch_name, "Character", ch_props)
            add_edge(a_id, ch_id, "HAS_CHARACTER")
            animes.append({"name": a_name, "score": float(a_props.get("score") or 0)})

        return {"character": display, "animes": animes, "nodes": list(nodes.values()), "edges": edges}

    @app.get("/api/studio")
    def api_studio(name: str, limit: int = 20):
        c = require_client()
        if c is None:
            return {"animes": [], "nodes": [], "edges": [], "error": "Neo4j 未配置"}

        # Resolve studio name with contains match
        resolve_cypher = """
        MATCH (s:Studio)
        WHERE toLower(s.name) CONTAINS toLower($raw)
        RETURN s.name as display
        LIMIT 1
        """
        rows = c.run(resolve_cypher, {"raw": name})
        display = rows[0]["display"] if rows else name

        nodes: Dict[str, Dict[str, Any]] = {}
        edges: List[Dict[str, Any]] = []
        edge_set = set()

        def add_node(node_id: str, label: str, ntype: str, props: Optional[Dict[str, Any]] = None):
            if node_id not in nodes:
                nodes[node_id] = {"id": node_id, "label": label, "type": ntype, "properties": props or {}}

        def add_edge(source: str, target: str, rtype: str):
            eid = f"{source}|{target}|{rtype}"
            if eid in edge_set: return
            edge_set.add(eid)
            edges.append({"id": eid, "source": source, "target": target, "type": rtype, "label": rtype})

        cypher = """
        MATCH (a:Anime)-[:PRODUCED_BY]->(s:Studio)
        WHERE toLower(s.name) = toLower($sname)
        RETURN a, s
        ORDER BY a.score DESC
        LIMIT $limit
        """
        rows = c.run(cypher, {"sname": display, "limit": int(limit)})
        animes = []
        for r in rows:
            a_node = r["a"]
            s_node = r["s"]
            a_props = _coerce_node_properties(a_node)
            s_props = _coerce_node_properties(s_node)
            a_name = a_props.get("name_cn") or a_props.get("name")
            s_name = s_props.get("name")
            a_id = f"Anime::{a_name}"
            s_id = f"Studio::{s_name}"
            add_node(a_id, a_name, "Anime", a_props)
            add_node(s_id, s_name, "Studio", s_props)
            add_edge(a_id, s_id, "PRODUCED_BY")
            animes.append({"name": a_name, "score": float(a_props.get("score") or 0)})

        return {"studio": display, "animes": animes, "nodes": list(nodes.values()), "edges": edges}

    @app.get("/api/discover")
    def api_discover(rank: int = 500, tags: int = 5, limit: int = 20):
        c = require_client()
        if c is None:
            return {"animes": [], "error": "Neo4j 未配置"}

        # rank is usually lower = better (e.g. rank 1 is top).
        # So we filter for animes with rank <= $rank_max.
        cypher = """
        MATCH (a:Anime)-[:HAS_TAG]->(t:Tag)
        WHERE a.rank <= $rank_max AND a.rank > 0
        WITH a, count(distinct t) as tagCount, collect(distinct t.name) as matchedTags
        WHERE tagCount >= $tag_min
        RETURN coalesce(a.name_cn, a.name) as anime, a.rank as rank, tagCount, matchedTags
        ORDER BY a.rank ASC, tagCount DESC
        LIMIT $limit
        """
        rows = c.run(
            cypher,
            {
                "rank_max": int(rank),
                "tag_min": int(tags),
                "limit": int(limit),
            },
        )
        animes = [
            {"name": r["anime"], "score": 0, "rank": int(r["rank"]) if r.get("rank") is not None else None, "tagCount": int(r["tagCount"]) if r.get("tagCount") is not None else 0, "matchedTags": r.get("matchedTags") or []}
            for r in rows
        ]
        return {"animes": animes}

    @app.get("/api/anime")
    def api_anime(name: str):
        c = require_client()
        if c is None:
            return {"found": False, "error": "Neo4j 未配置：请先在 backend/.env 填写 Neo4j 连接信息。"}
        return get_anime_detail(c, name=name)

    def _llm_resolve_entity(entity_name: str, category: str = "character") -> str:
        """
        Use LLM to translate English names to Japanese/Chinese as stored in the DB.
        e.g., Saber -> セイバー
        """
        if not settings.OPENAI_API_KEY:
            return entity_name
        
        system = (
            "You are an anime database expert. Translate the user's entity name into its original Japanese name (Kanji/Kana) "
            "or the exact Chinese title used in major databases (like MyAnimeList or Bangumi). "
            "Output ONLY the translated name, nothing else."
        )
        user = f"Entity Category: {category}\nEntity Name: {entity_name}\nTranslated Name:"
        
        try:
            url = f"{settings.OPENAI_BASE_URL}/chat/completions"
            headers = {"Authorization": f"Bearer {settings.OPENAI_API_KEY}", "Content-Type": "application/json"}
            body = {
                "model": settings.OPENAI_MODEL,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                "temperature": 0.0,
                "max_tokens": 50
            }
            req_obj = request.Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
            with request.urlopen(req_obj, timeout=10) as resp:
                resp_body = json.loads(resp.read().decode("utf-8"))
            resolved = resp_body["choices"][0]["message"]["content"].strip().replace("《", "").replace("》", "")
            print(f">>> [ENTITY RESOLVE] '{entity_name}' -> '{resolved}'")
            return resolved
        except Exception as e:
            print(f">>> [ENTITY RESOLVE ERROR] {e}")
            return entity_name

    @app.post("/api/chat", response_model=ChatResponse)
    def api_chat(req: ChatRequest):
        c = require_client()
        if c is None:
            return ChatResponse(
                answer="Neo4j 未配置：请先在 `backend/.env` 填写 NEO4J 连接信息。",
                recommendations=[],
                graph_paths=[],
            )

        parsed = _parse_intent(req.query)
        intent = parsed.get("intent")
        
        # If LLM is available and regex failed to find a specific intent (fallback to search),
        # try to use LLM to parse intent more accurately.
        if intent == "search" and settings.OPENAI_API_KEY:
            try:
                system = (
                    "Parse the user's anime-related question into a JSON intent. "
                    "Available intents: 'similar_anime' (target), 'character_casting' (character), 'casting_by_tags' (tags list), 'studio_works' (studio), 'character_appears' (character), 'tag_intersection' (tags list), 'search' (q). "
                    "If the user asks 'Recommend some anime like X', intent is 'similar_anime' and target is 'X'. "
                    "If the user asks 'Who voices X', intent is 'character_casting' and character is 'X'. "
                    "Output ONLY valid JSON."
                )
                user = f"User Question: {req.query}"
                url = f"{settings.OPENAI_BASE_URL}/chat/completions"
                headers = {"Authorization": f"Bearer {settings.OPENAI_API_KEY}", "Content-Type": "application/json"}
                body = {
                    "model": settings.OPENAI_MODEL,
                    "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                    "temperature": 0.0,
                    "response_format": {"type": "json_object"}
                }
                req_obj_parse = request.Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
                with request.urlopen(req_obj_parse, timeout=10) as resp:
                    resp_body = json.loads(resp.read().decode("utf-8"))
                llm_parsed = json.loads(resp_body["choices"][0]["message"]["content"])
                if llm_parsed.get("intent") and llm_parsed["intent"] != "search":
                    parsed = llm_parsed
                    intent = parsed["intent"]
                    print(f">>> [LLM INTENT PARSE SUCCESS] {intent}: {parsed}")
            except Exception as e:
                print(f">>> [LLM INTENT PARSE ERROR] {e}")
                pass

        print(f"\n>>> [CHAT DEBUG] Query: '{req.query}'")
        print(f">>> [CHAT DEBUG] Parsed Intent: {intent}")
        if "target" in parsed: print(f">>> [CHAT DEBUG] Target: '{parsed['target']}'")
        if "character" in parsed: print(f">>> [CHAT DEBUG] Character: '{parsed['character']}'")
        if "studio" in parsed: print(f">>> [CHAT DEBUG] Studio: '{parsed['studio']}'")
        if "tags" in parsed: print(f">>> [CHAT DEBUG] Tags: {parsed['tags']}")
        print("-" * 30)

        if intent == "similar_anime":
            target = parsed.get("target") or ""
            # Try to resolve anime title
            payload = recommend_similar_anime(c, target=target, limit=10)
            if not payload.get("recommendations"):
                resolved_target = _llm_resolve_entity(target, "anime title")
                if resolved_target != target:
                    payload = recommend_similar_anime(c, target=resolved_target, limit=10)
            
            resp = ChatResponse(**payload)
            llm_ans, llm_keywords = _llm_generate_answer(req.query, resp)
            if llm_ans: resp.answer = llm_ans
            if llm_keywords: resp.keywords = llm_keywords
            return resp

        if intent == "tag_intersection":
            tags = parsed.get("tags") or []
            payload = recommend_by_tags(c, tags=tags, limit=10)
            resp = ChatResponse(**payload)
            llm_ans, llm_keywords = _llm_generate_answer(req.query, resp)
            if llm_ans: resp.answer = llm_ans
            if llm_keywords: resp.keywords = llm_keywords
            return resp

        if intent == "character_casting":
            character = parsed.get("character") or ""
            def query_va(name):
                return c.run("""
                    MATCH (ch:Character)-[:VOICED_BY]->(v:VoiceActor)
                    WHERE toLower(ch.name) CONTAINS toLower($cname)
                    RETURN ch.name as character, v.name as voiceActor
                    LIMIT 5
                """, {"cname": name})
            
            rows = query_va(character)
            if not rows:
                resolved_char = _llm_resolve_entity(character, "character")
                if resolved_char != character:
                    rows = query_va(resolved_char)
            
            if rows:
                va = rows[0]["voiceActor"]
                ch_real = rows[0]["character"]
                works = c.run("""
                    MATCH (v:VoiceActor {name: $vname})<-[:VOICED_BY]-(:Character)<-[:HAS_CHARACTER]-(a:Anime)
                    RETURN coalesce(a.name_cn, a.name) as anime
                    LIMIT 5
                """, {"vname": va})
                recs = [{"name": r["anime"], "score": 100} for r in works]
                answer = f"The character <{ch_real}> is voiced by <{va}>. This voice actor also worked on: " + ", ".join([f"<{r['name']}>" for r in recs])
                resp = ChatResponse(answer=answer, recommendations=recs, graph_paths=[])
            else:
                resp = ChatResponse(answer=f"Sorry, I couldn't find the voice actor for <{character}> in my records.", recommendations=[], graph_paths=[])
            
            llm_ans, llm_keywords = _llm_generate_answer(req.query, resp)
            if llm_ans: resp.answer = llm_ans
            if llm_keywords: resp.keywords = llm_keywords
            return resp

        if intent == "casting_by_tags":
            tags = parsed.get("tags") or []
            payload = api_casting(",".join(tags), limit=10) # Reuse existing logic
            # Convert VoiceActor to recommendations format
            recs = [{"name": va["name"], "score": va["score"]} for va in payload.get("voiceActors", [])]
            answer = f"Here are some voice actors who specialize in these themes: " + ", ".join([f"<{r['name']}>" for r in recs[:5]])
            resp = ChatResponse(answer=answer, recommendations=recs, graph_paths=[])
            llm_ans, llm_keywords = _llm_generate_answer(req.query, resp)
            if llm_ans: resp.answer = llm_ans
            if llm_keywords: resp.keywords = llm_keywords
            return resp

        if intent == "studio_works":
            studio = parsed.get("studio") or ""
            payload = api_studio(studio, limit=10)
            recs = payload.get("animes", [])
            if not recs:
                resolved_studio = _llm_resolve_entity(studio, "studio")
                if resolved_studio != studio:
                    payload = api_studio(resolved_studio, limit=10)
                    recs = payload.get("animes", [])
            
            s_name = payload.get("studio", studio)
            answer = f"I found several works produced by studio <{s_name}>: " + ", ".join([f"<{r['name']}>" for r in recs[:5]])
            resp = ChatResponse(answer=answer, recommendations=recs, graph_paths=[])
            llm_ans, llm_keywords = _llm_generate_answer(req.query, resp)
            if llm_ans: resp.answer = llm_ans
            if llm_keywords: resp.keywords = llm_keywords
            return resp

        if intent == "character_appears":
            character = parsed.get("character") or ""
            def query_appearance(name):
                # Resolve input character to a real Character.name in Neo4j
                resolve_cypher = """
                MATCH (c:Character)
                WHERE toLower(c.name) = toLower($raw) OR toLower(c.name) CONTAINS toLower($raw)
                RETURN c.name as display
                LIMIT 1
                """
                rows = c.run(resolve_cypher, {"raw": name})
                return rows[0]["display"] if rows else ""

            c_display = query_appearance(character)
            if not c_display:
                resolved_char = _llm_resolve_entity(character, "character")
                if resolved_char != character:
                    c_display = query_appearance(resolved_char)
            
            if not c_display: c_display = character

            # Find animes that have this character.
            cypher = """
            MATCH (a:Anime)-[:HAS_CHARACTER]->(c:Character)
            WHERE toLower(c.name) = toLower($cname)
            RETURN coalesce(a.name_cn, a.name) as anime, count(*) as score
            ORDER BY score DESC
            LIMIT 10
            """
            rows = c.run(cypher, {"cname": c_display})
            recommendations = [{"name": r["anime"], "score": int(r["score"]), "matchedTags": []} for r in rows]
            graph_paths = []
            for rec in recommendations[:3]:
                graph_paths.append(
                    {
                        "source": f"Character::{c_display}",
                        "target": rec["name"],
                        "viaTags": [c_display],
                        "edges": [
                            {"source": f"Anime::{rec['name']}", "target": f"Character::{c_display}", "type": "HAS_CHARACTER"}
                        ],
                    }
                )
            answer = f"Works featuring the character <{character}> (matched as <{c_display}>) include: "
            if recommendations:
                answer += ", ".join([f"<{x['name']}>" for x in recommendations[:5]])
            else:
                answer += " (No matching works found in the current graph)"
            resp = ChatResponse(answer=answer, recommendations=recommendations, graph_paths=graph_paths)
            llm_ans, llm_keywords = _llm_generate_answer(req.query, resp)
            if llm_ans: resp.answer = llm_ans
            if llm_keywords: resp.keywords = llm_keywords
            return resp

        # Fallback: search
        q = parsed.get("q") or req.query
        recs = search_anime(c, q=q, limit=10)
        graph_paths: List[Dict[str, Any]] = []
        for rec in recs[:3]:
            graph_paths.append(
                {
                    "source": "SEARCH",
                    "target": rec["name"],
                    "viaTags": rec.get("matchedTags", [])[:5],
                    "edges": [{"source": f"Tag::{t}", "target": f"Anime::{rec['name']}", "type": "HAS_TAG"} for t in (rec.get("matchedTags") or [])[:5]],
                }
            )
        answer = f"I found these results for '{q}' in the graph: "
        if recs:
            answer += ", ".join([f"<{x['name']}>" for x in recs[:8]])
        else:
            answer += "(No matches found)"
        resp = ChatResponse(answer=answer, recommendations=recs, graph_paths=graph_paths)
        llm_ans, llm_keywords = _llm_generate_answer(req.query, resp)
        if llm_ans: resp.answer = llm_ans
        if llm_keywords: resp.keywords = llm_keywords
        return resp

    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn
    # This ensures the server stays running when you run `python3 backend/main.py`
    uvicorn.run(app, host="0.0.0.0", port=8000)

