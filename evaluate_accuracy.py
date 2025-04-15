import json
import csv
import os
from sklearn.metrics import confusion_matrix, classification_report
import matplotlib.pyplot as plt
import seaborn as sns

# === Load model outputs ===
with open("output/parsed_output.json", "r", encoding="utf-8") as f:
    model_outputs = json.load(f)

# === Load PolitiFact dataset ===
with open("data/politifact_factcheck_data.json", "r", encoding="utf-8") as f:
    politifact_raw = [json.loads(line) for line in f]

# === Verdict mapping
def map_verdict(label):
    label = label.lower().strip()
    return label in ["true", "mostly-true", "half-true"]

# === Build lookup
truth_lookup = {entry["statement"]: map_verdict(entry["verdict"]) for entry in politifact_raw}

# === Compare and collect results
results = []
y_true = []
y_pred = []
unmatched = []

for entry in model_outputs:
    statement = entry["fact"]
    model_verdict = entry["verdict"]

    if model_verdict not in ["True", "False"]:
        continue

    if statement in truth_lookup:
        predicted = model_verdict == "True"
        actual = truth_lookup[statement]

        y_true.append(actual)
        y_pred.append(predicted)

        results.append({
            "statement": statement,
            "actual_verdict": actual,
            "model_verdict": predicted
        })
    else:
        unmatched.append(statement)

# === Save CSV
csv_path = "output/verdict_comparison.csv"
with open(csv_path, "w", newline="", encoding="utf-8") as csvfile:
    writer = csv.DictWriter(csvfile, fieldnames=["statement", "actual_verdict", "model_verdict"])
    writer.writeheader()
    writer.writerows(results)

# === Accuracy and Confusion Matrix
total = len(results)
correct = sum(1 for r in results if r["actual_verdict"] == r["model_verdict"])
accuracy = correct / total if total > 0 else 0

print(f"\n✅ Saved CSV to: {csv_path}")
print(f"🎯 Accuracy: {accuracy:.4f}")
print(f"🧪 Total comparisons: {total}")
print(f"❌ Unmatched: {len(unmatched)}")

# === Show confusion matrix
cm = confusion_matrix(y_true, y_pred)
labels = ["False", "True"]

plt.figure(figsize=(6, 5))
sns.heatmap(cm, annot=True, fmt='d', cmap='Blues', xticklabels=labels, yticklabels=labels)
plt.title("Confusion Matrix")
plt.xlabel("Predicted")
plt.ylabel("Actual")
plt.tight_layout()
plt.savefig("output/confusion_matrix.png")
plt.show()

# === Classification Report
print("\n📊 Classification Report:")
print(classification_report(y_true, y_pred, target_names=labels))