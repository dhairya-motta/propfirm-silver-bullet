import pandas as pd
import time
import os

print("Loading old dataset...")
old_df = pd.read_csv(r'C:\Users\kingcuber\.gemini\antigravity-ide\scratch\nsx_cleaned_2010_2024.csv')
old_df['datetime'] = pd.to_datetime(old_df['timestamp'], utc=True)
max_date = old_df['datetime'].max()
print(f"Max date in old dataset: {max_date}")
# Drop datetime column, we just needed it for max_date
old_df.drop(columns=['datetime'], inplace=True)

print("Loading new dataset...")
new_df = pd.read_csv(r'C:\Users\kingcuber\Desktop\algoRange\Dataset_NQ_1min_2022_2025.csv')
print(f"Loaded {len(new_df)} rows from new dataset.")

# Parse the timestamp ET column
print("Parsing dates...")
# the format is '12/26/2022 18:01'
new_df['parsed_dt'] = pd.to_datetime(new_df['timestamp ET'], format='%m/%d/%Y %H:%M')
# It's ET time, so localize to US/Eastern
new_df['parsed_dt'] = new_df['parsed_dt'].dt.tz_localize('US/Eastern', ambiguous='infer', nonexistent='shift_forward')

# Filter for rows strictly after the old dataset max date
# Note: old max date is UTC. We can compare directly since parsed_dt is timezone-aware
utc_dt = new_df['parsed_dt'].dt.tz_convert('UTC')
new_df_filtered = new_df[utc_dt > max_date].copy()

print(f"Filtered to {len(new_df_filtered)} rows that are newer than the old dataset.")

# Format the timestamp column to match the old one
new_df_filtered['timestamp'] = new_df_filtered['parsed_dt'].dt.strftime('%Y-%m-%d %H:%M:%S%z')
# The %z will format like -0500, let's inject the colon to make it -05:00 if needed, or leave it. Pandas handles either.
new_df_filtered['timestamp'] = new_df_filtered['timestamp'].apply(lambda x: x[:-2] + ':' + x[-2:])

# keep only columns: timestamp,open,high,low,close,volume
new_df_filtered = new_df_filtered[['timestamp', 'open', 'high', 'low', 'close', 'volume']]

print("Concatenating datasets...")
merged_df = pd.concat([old_df, new_df_filtered], ignore_index=True)

output_file = r'C:\Users\kingcuber\.gemini\antigravity-ide\scratch\nsx_cleaned_2010_2025.csv'
merged_df.to_csv(output_file, index=False)
print(f"Saved {len(merged_df)} total rows to {output_file}!")
