import json
import matplotlib.pyplot as plt

# Define the file path
file_path = './dpo/eval_data_with_score.json'

# Read the JSON data from the file
with open(file_path, 'r') as file:
    data = json.load(file)

# Extract scores from the JSON data
scores = [entry['score'] for entry in data]

# Plotting
plt.figure(figsize=(8, 4))
plt.hist(scores, bins=15, edgecolor='black')
plt.title('Distribution of Scores')
plt.xlabel('Score')
plt.ylabel('Frequency')
plt.xlim(min(scores) - 1, max(scores) + 1)  # Adjust x-axis limit based on data range
plt.xticks(range(int(min(scores)), int(max(scores)) + 2, 5))
plt.show()
# Save the plot to a PDF file with 300 DPI
plt.savefig('score_distribution.pdf', format='pdf', dpi=300)
