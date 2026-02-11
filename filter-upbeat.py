import csv

# Input and output file paths
input_file = 'upbeat_global_data_2025.csv'
output_file = 'unique_utilities.csv'

# Use a set to track unique rows
unique_rows = set()

# Read the CSV and collect unique rows
with open(input_file, 'r', newline='', encoding='utf-8') as csvfile:
    reader = csv.reader(csvfile)
    header = next(reader)  # Read header
    for row in reader:
        # Convert row to tuple to make it hashable for the set
        unique_rows.add(tuple(row))

# Write the unique rows to a new CSV
with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
    writer = csv.writer(csvfile)
    writer.writerow(header)  # Write header
    for row in unique_rows:
        writer.writerow(row)

print(f"Unique entries written to '{output_file}'")
