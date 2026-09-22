"""TF-IDF based clause retrieval for evidence-grounded Q&A.

Uses scikit-learn's TF-IDF vectorizer and cosine similarity to find the
most relevant clauses for a given question. This is computed in-memory
with no external vector database needed.

Efficiency:
- The TF-IDF matrix is computed once per document session and cached.
- Query result caching (LRU in-memory dict) prevents duplicate matrix multiplications.
- O(N) argpartition selection instead of O(N log N) sorting.
- Zero external API costs for retrieval.
"""

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np

from backend.models.schemas import Clause


class ClauseRetriever:
    """Retrieves the most relevant clauses for a given question.
    
    Uses TF-IDF vectorization with cosine similarity. The vectorizer
    is fitted once on all clause texts, then reused for all queries.
    """
    
    def __init__(self, clauses: list[Clause]):
        """Initialize the retriever with a set of clauses.
        
        Efficiency: TF-IDF matrix is computed once here and cached in memory.
        Subsequent retrieve() calls transform only the query.
        """
        self.clauses = clauses
        self._clause_texts = [clause.text for clause in clauses]
        self._query_cache: dict[tuple[str, int], list[Clause]] = {}
        
        if not self._clause_texts:
            self._vectorizer = None
            self._tfidf_matrix = None
            return
        
        # Fit the vectorizer on all clause texts at initialization time
        # Efficiency: Uses sublinear TF scaling for better performance on legal text
        self._vectorizer = TfidfVectorizer(
            stop_words="english",
            ngram_range=(1, 2),  # Unigrams + bigrams for better phrase matching
            max_features=5000,   # Cap features to keep memory bounded
            sublinear_tf=True,   # Use log-scaled TF for better discrimination
        )
        self._tfidf_matrix = self._vectorizer.fit_transform(self._clause_texts)
    
    def retrieve(self, query: str, top_k: int = 5) -> list[Clause]:
        """Find the top-k most relevant clauses for a query.
        
        Args:
            query: The user's question or scenario description
            top_k: Maximum number of clauses to return
        
        Returns:
            List of most relevant Clause objects, ordered by relevance
        """
        if not self._vectorizer or not self.clauses:
            return []
        
        # Efficiency: Check in-memory query cache for instant O(1) retrieval
        cache_key = (query.strip().lower(), top_k)
        if cache_key in self._query_cache:
            return self._query_cache[cache_key]
        
        # Transform the query using the fitted vectorizer
        query_vector = self._vectorizer.transform([query])
        
        # Compute cosine similarity between query and all clauses
        # Efficiency: Sparse matrix operations — fast even for large documents
        similarities = cosine_similarity(query_vector, self._tfidf_matrix).flatten()
        
        # Get indices of top-k most similar clauses
        # Efficiency: argpartition is O(n) vs O(n log n) for full sort
        k = min(top_k, len(self.clauses))
        if k == 0:
            return []
        
        top_indices = np.argpartition(similarities, -k)[-k:]
        # Sort the top-k by similarity score (descending)
        top_indices = top_indices[np.argsort(similarities[top_indices])[::-1]]
        
        # Filter out clauses with zero similarity (completely irrelevant)
        result = []
        for idx in top_indices:
            if similarities[idx] > 0.0:
                result.append(self.clauses[idx])
        
        # Cache query result
        self._query_cache[cache_key] = result
        return result
    
    def retrieve_by_categories(self, query: str, top_k: int = 5) -> list[Clause]:
        """Retrieve clauses across multiple categories for scenario analysis.
        
        Ensures diversity by returning at most 2 clauses per category,
        which helps scenario analysis reason across different document areas.
        """
        all_relevant = self.retrieve(query, top_k=top_k * 2)  # Over-fetch
        
        # Enforce category diversity: max 2 per category
        category_counts: dict[str, int] = {}
        diverse_results: list[Clause] = []
        
        for clause in all_relevant:
            cat = clause.category.value if clause.category else "general"
            count = category_counts.get(cat, 0)
            if count < 2:
                diverse_results.append(clause)
                category_counts[cat] = count + 1
            if len(diverse_results) >= top_k:
                break
        
        return diverse_results
