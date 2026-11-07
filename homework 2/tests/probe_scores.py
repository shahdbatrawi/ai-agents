"""
probe_scores.py - print the real similarity scores for some queries, with NO cut-off.
Use it to choose SEARCH_MIN_SCORE from real numbers.

Run from the `homework 2` folder:
    python tests/probe_scores.py "MSU experience" "Harvard experience"
    python tests/probe_scores.py "AI skills" --tables skills
"""
import argparse
import os
import sys

sys.path.insert(0, os.getcwd())
from dotenv import load_dotenv

load_dotenv()
from flask_app.utils.database import database
from flask_app.utils.embeddings import EmbeddingError
from flask_app.utils.semantic_search import search_by_meaning

parser = argparse.ArgumentParser()
parser.add_argument("queries", nargs="+")
parser.add_argument("--tables", nargs="*", default=None)
parser.add_argument("--top", type=int, default=5)
args = parser.parse_args()

db = database()
for q in args.queries:
    print(f"\nQuery: {q!r}  tables={args.tables or 'all'}")
    try:
        results = search_by_meaning(db, q, tables=args.tables, top_k=args.top, min_score=-1.0)
    except EmbeddingError as error:
        print(f"  ERROR: {error}")
        continue
    for r in results:
        print(f"  {r['score']:.3f}  {r['table']}#{r['id']}  {r['text'][:70]}")