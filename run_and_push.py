import os
import subprocess
from datetime import datetime
from batch_fact_verifier import run_verification_batch

# === CONFIG ===
start = 0
end = 40
# commit_message = f"Auto-push results for range {start}-{end}"
commit_message = f"Another Commit to Add Auto Git Pusher"

# === Step 1: Run the batch verifier directly
print(f"🔍 Running batch_fact_verifier.py via function call (range {start}-{end})...")
run_verification_batch(start_idx=start, end_idx=end)

# === Step 2: Git push
print("\n✅ Finished processing. Now pushing to GitHub...")

# Files to track (edit if needed)
files_to_push = [
    "output/fact_results.json",
    "output/full_output.json",
    "output/parsed_output.json",
    "output/checkpoint.json"
]

# Push all
subprocess.run(["git", "add", "."], check=True)

# Stage files
# for file in files_to_push:
#     if os.path.exists(file):
#         subprocess.run(["git", "add", file], check=True)

timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
subprocess.run(["git", "commit", "-m", f"{commit_message} at {timestamp}"], check=True)
subprocess.run(["git", "push"], check=True)

print("\n🚀 All done! Outputs committed and pushed to GitHub.")
