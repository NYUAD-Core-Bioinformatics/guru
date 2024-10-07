#!/bin/bash
#This script search for Sample_Name and replace ".,()+" and whitespace with "_" on SampleSheet.csv file.
#for eg:-
#[Data]
#Sample_ID,Sample_Name,I7_Index_ID,index,I5_Index_ID,index2
#LIB2247,abc_L20230214-1_1a,Index 01,ATCACGAT,,
awk -i inplace  'BEGIN{FS=OFS=","}/^LIB[0-9]+,/{gsub(/[\." "()+<`\x27]/,"_",$2);print;next}1' file.csv


## Below validation is for replacing 0's from the samplename index field
awk -i inplace  'BEGIN{FS=OFS=","}/^*+,/{gsub(/[\." "<`\x27]/,"_",$2);print;next}1' file.csv
