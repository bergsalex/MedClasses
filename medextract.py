#!/bin/python
__author__ = 'aberger'

import sys
import getopt
import csv
import re
import requests


def print_help():
    print u'Usage: manage.py [OPTIONS] [INFILE]'
    print u'Attempt to extract classes of medication a patient prescribed using RxNav Api.'
    print u'Your file is assumed to have column headers.'
    print u"Prescibed info will be take from column with header 'Medications'"
    print u'Found classes will be appended  after existing columns'
    print u''
    print u'-d, --delimiter      specify the character on which the file is delimited. Default: ,'
    print u'-q, --quotechar      specify the character that starts/ends a quoted string. Default: "'
    print u'-i, --inflie         specify the input filename.'
    print u'-o, --outfile        specify the output filename. Default: processed.csv'
    print u'-h, --help           output this help text and exit'
    print u'-v, --version        output version information and exit.'

def update_progress_bar(current_row, row_count):
    per = int(round(current_row/row_count*100))
    pro = int(round(current_row/row_count*20))
    sys.stdout.write('\r')
    sys.stdout.write("[%-20s] %d%%" % ('='*pro, per))
    sys.stdout.flush()

def main(argv):
    VERSION = u'0.01'
    NORM_URI = u'https://rxnav.nlm.nih.gov/REST/rxcui.json'
    ING_URL = u'https://rxnav.nlm.nih.gov/REST/rxcui/%s/related.json'
    CLASS_URI = u'https://rxnav.nlm.nih.gov/REST/rxclass/class/byRxcui.json'
    inputfile = None
    outputfile = 'processed.csv'
    delimiter = ','
    quotechar = '"'
    # A list of words known not to be drugs
    skip_list = ('once', 'twice', 'daily', 'nightly', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday',
                 'Sunday', 'day', 'night', 'one', 'two', 'three', 'four', 'times', 'supplement', 'must', 'have', 'been',
                 'with', 'that', 'baby', 'listed')

# Command Line Argument Processing -------------------------------------------------------------------------------------
    try:
        opts, args = getopt.gnu_getopt(argv, "hvi:o:d:q:", ["help", "infile=", "outfile=", "delimiter", "quotechar"])
    except getopt.GetoptError:
        print_help()
        sys.exit(2)

    if len(args) > 0:
        inputfile = args[0]
    if len(args) > 1:
        outputfile = args[1]

    for opt, arg in opts:

        if opt in ("-h", "--help"):
            print_help()
            sys.exit()
        elif opt in ("-v", "--version"):
            print u'Medextract Version: '+VERSION
            sys.exit()
        elif opt in ("-i", "--infile"):
            inputfile = arg
        elif opt in ("-o", "--outfile"):
            outputfile = arg
        elif opt in ("-d", "--delimiter"):
            delimiter = arg
        elif opt in ("-q", "--quotechar"):
            quotechar = arg

    if inputfile is None:
        print_help()
        sys.exit(2)

# Begin Program Run ----------------------------------------------------------------------------------------------------
    update_progress_bar(0, 1)
    # Match all word groups made up of only letters
    reg_names = re.compile(r'\b[A-Za-z]{4,}')

    drug_name_cache = dict.fromkeys(skip_list)
    #drug_name_cache['Glucophage'] = -1

    unique_classes = []
    patient_classes = {}

    drug_id_cache = {}
    current_row = 0.0

    # Open input CSV File
    with open(inputfile, 'rb') as infile:
        reader = csv.reader(infile, delimiter=delimiter, quotechar=quotechar)

        # Count number of rows in input file
        row_count = sum(1 for row in reader)
        infile.seek(0)

        # Capture headers from input csv
        headers = reader.next()

        # Open output CSV File
        with open(outputfile, 'wb') as outfile:
            writer = csv.writer(outfile, delimiter=delimiter, quotechar=quotechar)
            writer.writerow(headers)

            for rows in reader:
                if len(rows[0]) > 0:
                    patient = {key: value for (key, value) in zip(headers, rows)}
                    rxclasses = []
                    drugs = reg_names.findall(patient['Medications'])
                    for drug in drugs:
                        # Check drug cache
                        if drug in drug_name_cache:
                            rxcui = drug_name_cache[drug]
                        else:
                            # Query RxNorm Drug API
                            rxcui = requests.get(NORM_URI, {'name': drug}).json()\
                                .get('idGroup', {}).get('rxnormId', [])
                            if len(rxcui) > 0:
                                rxcui = rxcui[0]
                                drug_name_cache[drug] = rxcui
                            else:
                                drug_name_cache[drug] = None

                        if rxcui:
                            # Check id cache
                            if rxcui in drug_id_cache:
                                classes = drug_id_cache[rxcui]
                                if classes:
                                    rxclasses.extend(classes)
                            else:
                                # Query RxClass Drug API
                                rxcl = requests.get(CLASS_URI, {'rxcui': rxcui}).json()\
                                    .get('rxclassDrugInfoList', {}).get('rxclassDrugInfo')

                                # If no result from RxClass Query
                                if not rxcl:
                                    # Check if the RxDrug ID was for a Brand, then extract ingredient ID if available
                                    ing_rxcui = requests.get(ING_URL % rxcui, {'tty': 'IN'}).json()\
                                        .get("relatedGroup", {}).get("conceptGroup", [])
                                    if len(ing_rxcui) > 0:
                                        ing_rxcui = ing_rxcui[0].get("conceptProperties", [])
                                        if len(ing_rxcui) > 0:
                                            ing_rxcui = ing_rxcui[0].get("rxcui")
                                            if ing_rxcui:
                                                rxcl = requests.get(CLASS_URI, {'rxcui': ing_rxcui}).json() \
                                                    .get('rxclassDrugInfoList', {}).get('rxclassDrugInfo')

                                # Extract Class names from RxClass JSON Object
                                if rxcl:
                                    classes = [item.get('rxclassMinConceptItem', {}).get('className')
                                               for item in rxcl if item.get('relaSource') == "ATC"]
                                    if len(classes) > 1:
                                        print drug
                                        print classes
                                else:
                                    classes = None

                                if classes:
                                    drug_id_cache[rxcui] = classes
                                    rxclasses.extend(classes)
                                else:
                                    drug_id_cache[rxcui] = None

                    # Write Row to Output CSV
                    writer.writerow(rows+rxclasses)
                    unique_classes.extend(rxclasses)
                    patient_classes[patient['Patient ID']+':'+patient_classes['age at testing']] = {'row': rows, 'classes': rxclasses}

                    # Update Progress Bar
                    current_row += 1
                    update_progress_bar(current_row, row_count)

    with open('columns.csv', 'wb') as outfile:
        writer = csv.writer(outfile, delimiter=delimiter, quotechar=quotechar)
        unique_classes = set(unique_classes)
        writer.writerow(headers+unique_classes)

    # Update Progress Bar
    update_progress_bar(1, 1)

    sys.exit()

if __name__ == "__main__":
    main(sys.argv[1:])
