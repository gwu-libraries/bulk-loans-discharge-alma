This script uses Alma's [Scan-In API](https://developers.exlibrisgroup.com/alma/apis/docs/bibs/UE9TVCAvYWxtYXdzL3YxL2JpYnMve21tc19pZH0vaG9sZGluZ3Mve2hvbGRpbmdfaWR9L2l0ZW1zL3tpdGVtX3BpZH0=/) to discharge loans from a CSV file containing the relevant system identifiers. The CSV can be generated from an Analytics report, and it should include columns for MMS Id, Holdings Id, and Item Id, the owning library code, and either a temporary or permanent location code.

An additional CSV is required to map each location code (temporary or permanent) to a circulation desk that is configured for discharges at that location. 

**The script does not currently handle discharging items from a mix of temporary and permanent locations. If this is desired, break the list of items into two sets: one containing those items in temporary locations, the other containing those items in their permanent locations.**

The script uses asynchronous methods to optimize API calls; up to 25 items can be scanned in per second. A column called "done" is added to the CSV data source in order to indicate those rows that have successfully been scanned in. 

In addition, JSON results from the API are stored to disk for use in troubleshooting items with errors. Results are returned in batches of 1000 items. When running from the command line, the script will output a snippet of the results returned from each batch. This is useful for monitoring for API errors during execution.

### Requirements ###

 - pyyaml==5.1.1
 - pandas==0.24.2
 - aiohttp==3.5.4

Tested on Python 3.7

### Setup ###

1. Configure an API key for the Alma Bibs API with read/write access.
2. Download or clone the contents of this repo.
3. In Analytics, copy both reports in the folder `Shared Folders/Community/Reports/Consortia/WRLC/Loans Discharge App` to your own folder. **Please don't edit the shared versions of these reports.**
4. Configure the report called `loans_by_user_group` to retrieve the items on loan in your IZ that you wish to discharge.
5. Run the Analytics report `items_to_discharge`. This report depends on the report from step 4 but contains the necessary system Id's for use with the Bibs API. Export this report as a CSV file.
6. Edit the `locations_to_circ.csv` file (or create a new one) mapping each (permanent or temporary) item location to a circulation desk configured to discharge items from that location. **This is necessary to ensure that discharged items do not generate reshelving requests in Alma.**
7. Edit the file `_loan_discharge_config.yml`:
   - Update the location of the CSV files from steps 5 and 6 (if they are not located in the same directory as the scripts). 
   - Paste your API key from step 1 into the `apikey` field.
   - Make sure the value of the `location_type` key matches the kind of location associated with the items to be discharged. Possible values are `temp` and `perm`.
   - Change the name of the file to `loan_discharge_config.yml` (removing the leading underscore).
8. Create a subdirectory called `data` in the directory that houses the scripts. The JSON returned by the API will be saved to this directory. 
9. Run the script `discharge_loans.py` from the command line: e.g., `python discharge_loans.py`