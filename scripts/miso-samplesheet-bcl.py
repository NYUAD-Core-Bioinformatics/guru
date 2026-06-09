#!/usr/bin/python
### This script used to connect to mysql miso instance and get the Samplesheet in bcl convert format.
import pymysql
import csv
import sys
import shutil
import re

read1="adpread1"
read2="adpread2"

conn = pymysql.connect(host='miso.abudhabi.nyu.edu', port=13307, user='tgaclims', password='yABuuqQqYG', database='lims', ssl_disabled='True')
cursor = conn.cursor()

runid = int(sys.argv[1])

query = 'SELECT distinct  l.name, l.alias , ind1.name,ind1.sequence, ind2.name, ind2.sequence FROM Run r  JOIN Run_SequencerPartitionContainer rspc ON rspc.Run_runId = %s  JOIN SequencerPartitionContainer spc ON spc.containerId = rspc.containers_containerId  JOIN _Partition part ON part.containerId = spc.containerId  JOIN Pool pool ON pool.poolId = part.pool_poolId  JOIN Pool_LibraryAliquot pla ON pla.poolId = pool.poolId  JOIN LibraryAliquot la ON la.aliquotId = pla.aliquotId  JOIN Library l ON l.libraryId = la.libraryId  JOIN Sample s ON s.sampleId = l.sample_sampleId  Join Indices ind1 ON  ind1.indexId =l.index1Id LEFT Join Indices ind2 ON  ind2.indexId =l.index2Id;'


cursor.execute(query, (runid,))
with open("SampleSheet.csv", "w", newline="") as outfile:

    # Write custom header block
    outfile.write("[Header]\n")
    outfile.write("FileFormatVersion,2\n\n")
    outfile.write("[BCLConvert_Settings]\n")
    outfile.write(f"AdapterRead1,{read1}\n")
    outfile.write(f"AdapterRead2,{read2}\n\n")
    outfile.write(f"[BCLConvert_Data]\n")

    writer = csv.writer(outfile)

    # Write CSV header
    writer.writerow(["Sample_ID", "index", "index2"])

    for row in cursor:
        #sample_id = row[1]
        sample_id = re.sub(r'[ .()+<\'"]', "_", row[1])
        index1 = row[3]
        index2 = row[5]

        writer.writerow([sample_id, index1, index2])
shutil.copyfile("SampleSheet.csv", "SampleSheet.csv-orig")
print(f"BCL Convert Samplesheet generated here -> SampleSheet.csv")
