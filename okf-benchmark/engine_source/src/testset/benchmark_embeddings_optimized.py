import json
import time
import os
import random
import torch
import pandas as pd
import numpy as np
from tqdm import tqdm
from sentence_transformers import SentenceTransformer
from src.match.semantic import SemanticMatcher

# Force single-threaded execution for FAISS/PyTorch stability on macOS ARM64
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["VECLIB_MAXIMUM_THREADS"] = "1"
os.environ["NUMEXPR_NUM_THREADS"] = "1"
os.environ["TOKENIZERS_PARALLELISM"] = "false"
torch.set_num_threads(1)

def main():
    df_all = pd.read_parquet("reports/canonical_cases_2021_2026.parquet")
    with open("reports/synthetic_testset.json", "r") as f:
        variants = json.load(f)
        
    para_variants_all = [v for v in variants if v["variant_type"] == "paraphrased"]
    
    # 1. Deterministically sample 1,000 cases from the canonical database
    # This keeps the benchmark extremely fast on CPU while remaining representative.
    cnrs_all = df_all["cnr"].tolist()
    random.seed(42)
    sample_cnrs = set(random.sample(cnrs_all, 1000))
    
    df_sample = df_all[df_all["cnr"].isin(sample_cnrs)].copy()
    para_variants_sample = [v for v in para_variants_all if v["original_case_id"] in sample_cnrs]
    
    print(f"Selected {len(df_sample)} canonical cases and {len(para_variants_sample)} paraphrased variants for benchmarking.", flush=True)
    
    models_to_test = {
        "all-MiniLM-L6-v2": "sentence-transformers/all-MiniLM-L6-v2",
        "all-mpnet-base-v2": "sentence-transformers/all-mpnet-base-v2",
        "InLegalBERT": "law-ai/InLegalBERT"
    }
    
    results = []
    
    for name, path in models_to_test.items():
        print(f"\n==========================================", flush=True)
        print(f"Benchmarking model: {name} ({path})", flush=True)
        print(f"==========================================", flush=True)
        
        # Instantiate matcher
        matcher = SemanticMatcher()
        matcher.hybrid_enabled = True
        
        # Load custom model
        print("Loading model weights...", flush=True)
        matcher.model = SentenceTransformer(path)
        
        # Measure Index Build Time
        start_build = time.time()
        print("Building multi-chunk hybrid index...", flush=True)
        matcher.build_index(df_sample)
        build_time = time.time() - start_build
        print(f"Index build completed in {build_time:.2f} seconds.", flush=True)
        
        # Evaluate on the paraphrased variants of the sampled cases
        correct = 0
        fp = 0
        no_match = 0
        
        start_eval = time.time()
        for v in tqdm(para_variants_sample, desc=f"Evaluating {name}", mininterval=1.0):
            orig_id = v["original_case_id"]
            q_rec = v["variant_content"]
            
            res_list = matcher.search(q_rec, top_k=1, threshold=0.75)
            
            if not res_list or not res_list[0]["matched"]:
                no_match += 1
            else:
                matched_id = res_list[0]["matched_case_id"]
                if matched_id == orig_id:
                    correct += 1
                else:
                    fp += 1
                    
        eval_time = time.time() - start_eval
        print(f"Completed evaluation of {len(para_variants_sample)} variants in {eval_time:.2f} seconds.", flush=True)
        
        accuracy = (correct / len(para_variants_sample)) * 100
        
        results.append({
            "Model Name": name,
            "Accuracy (%)": round(accuracy, 2),
            "Correct Matches": correct,
            "False Positives": fp,
            "No Match": no_match,
            "Index Build Time (s)": round(build_time, 2),
            "Evaluation Time (s)": round(eval_time, 2)
        })
        
    # Compile comparison markdown table
    df_res = pd.DataFrame(results)
    print("\nBenchmark Results Table:", flush=True)
    print(df_res.to_markdown(index=False), flush=True)
    
    # Save results to a json file
    with open("reports/model_comparison_results.json", "w") as f:
        json.dump(results, f, indent=4)

if __name__ == "__main__":
    main()
