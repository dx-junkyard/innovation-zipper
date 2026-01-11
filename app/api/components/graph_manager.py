import os
from neo4j import GraphDatabase
from typing import List, Dict, Any, Optional

class GraphManager:
    # Node Labels
    LABEL_USER = "User"
    LABEL_CONCEPT = "Concept"
    LABEL_KEYWORD = "Keyword"
    LABEL_HYPOTHESIS = "Hypothesis"
    LABEL_DOCUMENT = "Document"
    LABEL_DOCUMENT_CHUNK = "DocumentChunk"

    # Edge Types
    REL_INTERESTED_IN = "INTERESTED_IN"
    REL_BELONGS_TO = "BELONGS_TO"
    REL_MENTIONED_IN = "MENTIONED_IN"
    REL_PART_OF = "PART_OF"
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

    def delete_user_interest(self, user_id: str, concept_name: str):
        """Removes the INTERESTED_IN relationship between User and Concept."""
        if not self.driver: return

        query = f"""
        MATCH (u:{self.LABEL_USER} {{id: $user_id}})-[r:{self.REL_INTERESTED_IN}]->(c:{self.LABEL_CONCEPT} {{name: $name}})
        DELETE r
        """
        try:
            with self.driver.session() as session:
                session.run(query, user_id=user_id, name=concept_name)
        except Exception as e:
            print(f"Error deleting user interest: {e}")

    def add_category_and_keywords(self, user_id: str, category_name: str, confidence: float, keywords: List[str], source_type: str = "ai_inferred"):
        """
        Adds a category and its keywords to the user's interest graph.
        User -> INTERESTED_IN -> Concept
        User -> INTERESTED_IN -> Keyword
        Keyword -> BELONGS_TO -> Concept
        """
        if not self.driver: return

        self.add_user_interest(user_id, category_name, confidence, source_type)

        if not keywords:
            return

        query = f"""
        MATCH (u:{self.LABEL_USER} {{id: $user_id}})
        MATCH (c:{self.LABEL_CONCEPT} {{name: $category_name}})

        UNWIND $keywords as kw
        MERGE (k:{self.LABEL_KEYWORD} {{name: kw}})

        // Link User to Keyword
        MERGE (u)-[r1:{self.REL_INTERESTED_IN}]->(k)
        SET r1.confidence = $confidence, r1.source_type = $source_type, r1.updated_at = datetime()

        // Link Keyword to Concept
        MERGE (k)-[r2:{self.REL_BELONGS_TO}]->(c)
        """
        try:
            with self.driver.session() as session:
                session.run(query, user_id=user_id, category_name=category_name, keywords=keywords, confidence=confidence, source_type=source_type)
        except Exception as e:
            print(f"Error adding structured interests: {e}")

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

    def add_document(self, text: str, file_id: str = None, url: str = None, properties: Dict[str, Any] = None):
        """Adds a Document node (representing the file)."""
        if not self.driver: return
        query = f"""
        MERGE (d:{self.LABEL_DOCUMENT} {{text: $text}})
        SET d.file_id = $file_id, d.url = $url
        SET d += $props
        RETURN d
        """
        try:
            with self.driver.session() as session:
                session.run(query, text=text, file_id=file_id, url=url, props=properties or {})
        except Exception as e:
            print(f"Error adding document: {e}")

    def add_chunk(self, text: str, evidence_ids: List[str] = None, properties: Dict[str, Any] = None):
        """Adds a DocumentChunk node."""
        if not self.driver: return
        query = f"""
        MERGE (dc:{self.LABEL_DOCUMENT_CHUNK} {{text: $text}})
        SET dc.evidence = $evidence
        SET dc += $props
        RETURN dc
        """
        try:
            with self.driver.session() as session:
                session.run(query, text=text, evidence=evidence_ids or [], props=properties or {})
        except Exception as e:
            print(f"Error adding chunk: {e}")

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

    def link_document_to_concept(self, document_text: str, concept_name: str, rel_type: str = "BELONGS_TO"):
        """Links a Document (File) to a Concept (Category)."""
        if not self.driver: return

        query = f"""
        MATCH (d:{self.LABEL_DOCUMENT} {{text: $d_text}})
        MATCH (c:{self.LABEL_CONCEPT} {{name: $c_name}})
        MERGE (d)-[r:{rel_type}]->(c)
        RETURN r
        """
        try:
            with self.driver.session() as session:
                session.run(query, d_text=document_text, c_name=concept_name)
        except Exception as e:
            print(f"Error linking document to concept: {e}")

    def link_document_to_keyword(self, document_text: str, keyword: str, rel_type: str = "TAGGED_WITH"):
        """Links a Document (File) to a Keyword."""
        if not self.driver: return

        query = f"""
        MATCH (d:{self.LABEL_DOCUMENT} {{text: $d_text}})
        MERGE (k:{self.LABEL_KEYWORD} {{name: $keyword}})
        MERGE (d)-[r:{rel_type}]->(k)
        RETURN r
        """
        try:
            with self.driver.session() as session:
                session.run(query, d_text=document_text, keyword=keyword)
        except Exception as e:
            print(f"Error linking document to keyword: {e}")

    def link_chunk_to_document(self, chunk_text: str, file_node_text: str, rel_type: str = "PART_OF"):
        """Links a DocumentChunk to a Document."""
        if not self.driver: return

        query = f"""
        MATCH (dc:{self.LABEL_DOCUMENT_CHUNK} {{text: $chunk_text}})
        MATCH (d:{self.LABEL_DOCUMENT} {{text: $file_text}})
        MERGE (dc)-[r:{rel_type}]->(d)
        RETURN r
        """
        try:
            with self.driver.session() as session:
                session.run(query, chunk_text=chunk_text, file_text=file_node_text)
        except Exception as e:
            print(f"Error linking chunk to document: {e}")

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

    def get_central_concepts(self, user_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Retrieves 'Hub' concepts for the user based on degree centrality.
        These concepts are connected to many other nodes (Hypotheses, Keywords, etc.)
        and serve as good starting points for exploration.
        """
        if not self.driver: return []

        # Cypher Query Logic:
        # 1. Match Concepts that the user is interested in.
        # 2. Calculate the 'degree' (number of connections) for each Concept.
        #    Note: We count all relationships ((c)--()) to capture links to Hypotheses, Keywords, etc.
        # 3. Return the top N concepts with the highest degree.
        query = f"""
        MATCH (u:{self.LABEL_USER} {{id: $user_id}})-[:{self.REL_INTERESTED_IN}]->(c:{self.LABEL_CONCEPT})

        // Calculate the degree using COUNT subquery (escaped for f-string)
        WITH c, COUNT {{ (c)--() }} as degree

        WHERE degree > 0
        RETURN c.name as name, degree
        ORDER BY degree DESC
        LIMIT $limit
        """

        results = []
        try:
            with self.driver.session() as session:
                result = session.run(query, user_id=user_id, limit=limit)
                for record in result:
                    results.append(record.data())
        except Exception as e:
            print(f"Error retrieving central concepts: {e}")

        return results

    def get_node_neighbors(self, user_id: str, node_id: str) -> Dict[str, List[Any]]:
        """
        Retrieves immediate neighbors of a specific node.
        Used for 'expanding' a node in the UI.
        """
        if not self.driver: return {"nodes": [], "edges": []}

        # [FIX] id()関数をelementId()に置き換えて警告を解消
        # elementId()はNeo4j 5.x以降で推奨される一意な識別子取得関数です
        query = f"""
        MATCH (u:{self.LABEL_USER} {{id: $user_id}})
        MATCH (center) WHERE center.name = $node_id

        MATCH (center)-[r]-(neighbor)
        RETURN
            {{id: coalesce(center.name, center.text, elementId(center)), label: coalesce(center.name, center.text, "No Label"), labels: labels(center), properties: properties(center)}} as center_node,
            {{source: coalesce(startNode(r).name, startNode(r).text, elementId(startNode(r))), target: coalesce(endNode(r).name, endNode(r).text, elementId(endNode(r))), label: type(r)}} as edge_data,
            {{id: coalesce(neighbor.name, neighbor.text, elementId(neighbor)), label: coalesce(neighbor.name, neighbor.text, "No Label"), labels: labels(neighbor), properties: properties(neighbor)}} as neighbor_node
        LIMIT 50
        """

        nodes_map = {}
        edges_list = []

        try:
            with self.driver.session() as session:
                result = session.run(query, user_id=user_id, node_id=node_id)
                for record in result:
                    # ノードの重複排除
                    c_node = record["center_node"]
                    n_node = record["neighbor_node"]
                    nodes_map[c_node["id"]] = c_node
                    nodes_map[n_node["id"]] = n_node

                    # エッジの追加
                    edges_list.append(record["edge_data"])

        except Exception as e:
            print(f"Error getting neighbors: {e}")

        return {
            "nodes": list(nodes_map.values()),
            "edges": edges_list
        }

    def clear_database(self):
        """Clears the entire graph (Use with caution!)."""
        if not self.driver: return
        query = "MATCH (n) DETACH DELETE n"
        try:
            with self.driver.session() as session:
                session.run(query)
        except Exception as e:
            print(f"Error clearing database: {e}")
