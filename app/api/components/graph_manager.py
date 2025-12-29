import os
from neo4j import GraphDatabase
from typing import List, Dict, Any, Optional

class GraphManager:
    # Node Labels
    LABEL_USER = "User"
    LABEL_CONCEPT = "Concept"
    LABEL_HYPOTHESIS = "Hypothesis"
    LABEL_DOCUMENT = "Document"

    # Edge Types
    REL_INTERESTED_IN = "INTERESTED_IN"
    REL_MENTIONED_IN = "MENTIONED_IN"
    REL_IMPLIES = "IMPLIES"
    REL_VERIFIED_BY = "VERIFIED_BY"

    # Source Types
    SOURCE_BASE = "base"
    SOURCE_USER_OBSERVED = "user_observed"
    SOURCE_USER_STATED = "user_stated"
    SOURCE_AI_INFERRED = "ai_inferred"

    def __init__(self, uri: Optional[str] = None, user: Optional[str] = None, password: Optional[str] = None):
        self.uri = uri or os.getenv("NEO4J_URI", "bolt://localhost:7687")
        self.user = user or os.getenv("NEO4J_USER", "neo4j")
        self.password = password or os.getenv("NEO4J_PASSWORD", "password")
        self.driver = None
        try:
            self.driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))
            self.verify_connection()
        except Exception as e:
            print(f"Failed to initialize Neo4j driver: {e}")

    def close(self):
        if self.driver:
            self.driver.close()

    def verify_connection(self):
        if self.driver:
            self.driver.verify_connectivity()

    def add_user(self, user_id: str):
        """Ensures a User node exists."""
        if not self.driver: return
        query = f"""
        MERGE (u:{self.LABEL_USER} {{id: $user_id}})
        RETURN u
        """
        try:
            with self.driver.session() as session:
                session.run(query, user_id=user_id)
        except Exception as e:
            print(f"Error adding user node: {e}")

    def add_concept(self, name: str, properties: Dict[str, Any] = None):
        """Ensures a Concept node exists."""
        if not self.driver: return
        query = f"""
        MERGE (c:{self.LABEL_CONCEPT} {{name: $name}})
        SET c += $props
        RETURN c
        """
        props = properties or {}
        try:
            with self.driver.session() as session:
                session.run(query, name=name, props=props)
        except Exception as e:
            print(f"Error adding concept node: {e}")

    def add_user_interest(self, user_id: str, concept_name: str, confidence: float = 1.0, source_type: str = "user_stated"):
        """Creates an INTERESTED_IN relationship between User and Concept."""
        if not self.driver: return

        # Ensure nodes exist
        self.add_user(user_id)
        self.add_concept(concept_name)

        query = f"""
        MATCH (u:{self.LABEL_USER} {{id: $user_id}})
        MATCH (c:{self.LABEL_CONCEPT} {{name: $name}})
        MERGE (u)-[r:{self.REL_INTERESTED_IN}]->(c)
        SET r.confidence = $confidence,
            r.source_type = $source_type,
            r.updated_at = datetime()
        RETURN r
        """
        try:
            with self.driver.session() as session:
                session.run(query, user_id=user_id, name=concept_name, confidence=confidence, source_type=source_type)
        except Exception as e:
            print(f"Error adding interest edge: {e}")

    def add_hypothesis(self, text: str, evidence_ids: List[str] = None, properties: Dict[str, Any] = None):
        """Adds a Hypothesis node."""
        if not self.driver: return
        query = f"""
        MERGE (h:{self.LABEL_HYPOTHESIS} {{text: $text}})
        SET h.evidence = $evidence
        SET h += $props
        RETURN h
        """
        try:
            with self.driver.session() as session:
                session.run(query, text=text, evidence=evidence_ids or [], props=properties or {})
        except Exception as e:
            print(f"Error adding hypothesis: {e}")

    def link_hypothesis_to_concept(self, hypothesis_text: str, concept_name: str, rel_type: str = "IMPLIES"):
        """Links a Hypothesis to a Concept (or vice versa depending on logic, here we assume Hypothesis IMPLIES Concept or relates to it)."""
        if not self.driver: return

        # We might need flexible direction or types, but for now let's assume Hypothesis -> Concept
        query = f"""
        MATCH (h:{self.LABEL_HYPOTHESIS} {{text: $h_text}})
        MATCH (c:{self.LABEL_CONCEPT} {{name: $c_name}})
        MERGE (h)-[r:{rel_type}]->(c)
        RETURN r
        """
        try:
            with self.driver.session() as session:
                session.run(query, h_text=hypothesis_text, c_name=concept_name)
        except Exception as e:
            print(f"Error linking hypothesis to concept: {e}")

    def get_user_interests(self, user_id: str) -> List[Dict[str, Any]]:
        """Retrieves concepts the user is interested in."""
        if not self.driver: return []
        query = f"""
        MATCH (u:{self.LABEL_USER} {{id: $user_id}})-[r:{self.REL_INTERESTED_IN}]->(c:{self.LABEL_CONCEPT})
        RETURN c.name as name, r.confidence as confidence, r.source_type as source_type
        ORDER BY r.confidence DESC
        """
        results = []
        try:
            with self.driver.session() as session:
                result = session.run(query, user_id=user_id)
                for record in result:
                    results.append(record.data())
        except Exception as e:
            print(f"Error retrieving user interests: {e}")
        return results

    def clear_database(self):
        """Clears the entire graph (Use with caution!)."""
        if not self.driver: return
        query = "MATCH (n) DETACH DELETE n"
        try:
            with self.driver.session() as session:
                session.run(query)
        except Exception as e:
            print(f"Error clearing database: {e}")
