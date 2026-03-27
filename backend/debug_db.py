
import os
from pathlib import Path
from dotenv import load_dotenv
from neo4j import GraphDatabase

load_dotenv(Path(__file__).parent / ".env")

URI = os.getenv("NEO4J_URI")
USER = os.getenv("NEO4J_USERNAME")
PWD = os.getenv("NEO4J_PASSWORD")

def run_query(query, params=None):
    with GraphDatabase.driver(URI, auth=(USER, PWD)) as driver:
        with driver.session() as session:
            result = session.run(query, params or {})
            return [record.data() for record in result]

print("--- Checking Anime 'Code Geass' ---")
q1 = "MATCH (a:Anime) WHERE toLower(coalesce(a.name_cn, a.name)) CONTAINS 'code geass' RETURN a.name as name, a.name_cn as name_cn LIMIT 5"
print(run_query(q1))

print("\n--- Checking Relationships for 'Code Geass' ---")
q6 = """
MATCH (a:Anime)-[r]->(target)
WHERE toLower(coalesce(a.name_cn, a.name)) CONTAINS 'code geass'
RETURN type(r) as rel_type, labels(target) as target_labels, count(*) as count
"""
print(run_query(q6))

print("\n--- Checking Relationships for 'セイバー' ---")
q7 = """
MATCH (c:Character)-[r]->(target)
WHERE c.name = 'セイバー'
RETURN type(r) as rel_type, labels(target) as target_labels, count(*) as count
"""
print(run_query(q7))
