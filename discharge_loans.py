import yaml
import pandas as pd
from async_fetch import run_batch
import asyncio
from pathlib import Path
from datetime import datetime

# Bibs API endpoint for scanning in items
SCAN_URL = 'https://api-na.hosted.exlibrisgroup.com/almaws/v1/bibs/{mms_id}/holdings/{holding_id}/items/{item_id}'
# Basic header for POST operation to scan endpoint
headers = {'Content-Type': 'application/json',
		   'Accept': 'application/json'}
# Basic parameters for use with POST op to scan endpoint
scan_params = {'op': 'scan',
			  'done': 'true'}

def load_loan_data(path_to_loans):
	'''Loads a CSV of items for discharge. CSV should include columns MMS Id, Holding Id, and Item Id.'''
	try:
		data = pd.read_csv(path_to_loans)
		return data
	except FileNotFoundError:
		print("Invalid path. loan-discharge-config.yml should include a path to a CSV file of item ID's for discharge.")
		return None 

def load_circ_desks(path_to_circ_desks):
	'''Loads a CSV mapping Alma temporary locations to a circ desks for reshelving. Should include columns  location_code and circ_desk.'''
	try:
		desks = pd.read_csv(path_to_circ_desks)
		return desks
	except FileNotFoundError:
		print("Invalid path. loan-discharge-config.yml should include a path to a CSV file mapping Alma temporary locations to their circulation desks for reshelving.")
		return None 

def convert_header(header):
	'''Helper function for converting Analytics report headers to a format for use in the Alma Bibs API.'''
	return header.lower().replace(' ', '_')

def prep_data(config):
	'''Loads and preps data for batch processing.'''
	items = load_loan_data(config['loans_data_file'])
	desks = load_circ_desks(config['circ_desks_file'])
	if items.empty or desks.empty:
		return None
	# Convert Analytics column names
	items.columns = [convert_header(c) for c in items.columns]
	# Add circ_desk column, matching on a location code
	# The config file should specify whether temp or perm
	if config['location_type'] == 'temp':
		location_column = 'temporary_location_code'
	elif config['location_type'] == 'perm':
		location_column = 'location_code'
	else:
		print('Invalid location_type provided in the config file. Possible values are "temp" and "perm."')
		return None
	try:
		items = items.merge(desks, 
						left_on=location_column,
						right_on='location_code')
	except KeyError:
		print('Invalid columns for matching each temporary location to its circ desk. The loans_data_file should have either a temporary_location_code or location_code column; the circ_desks_file should have a location_code column (which holds the temporary location code associated with each circ desk).')
		return None
	# Validate and convert DataFrame to list of records for feeding to the API in sequence
	# Return both the DF and the rows; the DF will be used to flag completed items
	if validate_data(items):
		return items
	return None

def validate_data(items):
	'''Checks to make sure the required columns are present for the data elements used by the API.
	Argument should be a DataFrame.'''
	try:
		assert {'mms_id', 'holding_id', 'item_id', 'circ_desk', 'library_code'}.issubset(items.columns)
		return True
	except AssertionError:
		print('Missing columns. Data set for discharge must include MMS Id, Holding Id, Item Id, Circ Desk, and Library Code columns.')
		return None


def extract_ids(response):
	'''Helper function to extract the system ID's from the API responses -- useful for tracking what we have left to do.
	Argument should be a JSON response from the Scan-In API.'''
	try:
		mms_id = response['bib_data']['mms_id']
		holding_id = response['holding_data']['holding_id']
		item_id = response['item_data']['pid']
		return {'mms_id': mms_id,
				'holding_id': holding_id,
			   'item_id': item_id}
	except Exception as e:
		return None

def test_on_shelf(item_response):
	'''Given a response object from the Scan-In API, verify that the item\'s base stauts is "In place."'''
	try:
		assert item_response['item_data']['base_status']['desc'] == 'Item in place'
		return extract_ids(item_response)
	except AssertionError:
		return False

def compute_remainder(results, data, test_fn):
	'''Given a partial list of results, identify those on the original dataset as completed.
	results should be a list of results from the run_batch function.
	data should be the original data set (as a DataFrame).
	test_fn should be a function that returns either a valid row in the data set or else None.'''
	completed = [test_fn(r['response']) for r in results]
	completed = pd.DataFrame.from_records([c for c in completed if c])
	if completed.empty:
		print("No rows could be completed. Please see results_batch.json for errors.")
		return pd.DataFrame()
	# Convert Id's from strings to int
	for c in completed.columns:
		completed[c] = completed[c].astype(int)
	# Add column marking the completed results
	completed['done'] = True
	return data.merge(completed, on=['mms_id', 
									'holding_id',
									'item_id'],
									how='left')

def param_fn(row):
	'''Function to generate params for the scan-in API for each row in the data.. 
		Updates the desk for discharge depending on the item's location.
		In this case, data to POST will be None.'''
	scan_params['circ_desk'] = row['circ_desk']
	scan_params['library'] = row['library_code']
	return scan_params, None

def do_scan_in(rows, config):
	'''Perform scan-in (using the run_batch function from async_fetch), accumulating results. '''
	headers['Authorization'] = 'apikey {}'.format(config['apikey'])
	loop = asyncio.get_event_loop()
	results = []
	print("Scanning in items...")
	for batched_result in run_batch(loop,
								rows,
								param_fn=param_fn,
								base_url=SCAN_URL,
								headers=headers,
								path_to_files=config['data_dir'],
								batch_size=1000,
								http_type='POST'):
		results.extend(batched_result)
	return results

def discharge_loans():
	'''Main function for running batch discharge.'''
	# Loading the config objects from YAML
	with open('./loan_discharge_config.yml', 'r') as f:
		config = yaml.load(f, Loader=yaml.FullLoader)
	data = prep_data(config)
	if data.empty:
		return None
	rows = [d._asdict() for d in data.itertuples(index=False)]
	results = do_scan_in(rows, config)
	print("Scan-in complete. Marking data set for successful discharges...")
	# Merge completed results with original data set
	data = compute_remainder(results=results, data=data, test_fn=test_on_shelf)
	if data.empty:
		return
	# Rename the file for clarity, adding today's date
	out_path = Path(config['loans_data_file'])
	new_file = out_path.stem + '_{}.csv'.format(datetime.now().strftime('%Y-%m-%d'))
	data.to_csv(out_path.parent / new_file, index=False)

if __name__ == '__main__':
	discharge_loans()