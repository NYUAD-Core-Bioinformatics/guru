#!/bin/bash
#Description: This script is used to reverse complement index2 barcodes from SampleSheet.csv generated from miso.
#Usage: sh demux-revComp.sh "Type yes or no"
#Note:- Place SampleSheet.csv named file on the current directory. Otherwise script fails
#Version: 1.1


#Defining execution parameters
if [ "$#" -eq  "0" ]
   then
     echo "Usage: sh demux-revComp.sh "yes" or "no" "
     echo "yes -> With reverse complement"
     echo "no -> Without reverse complement"
     exit
 fi


if [[ ! -f SampleSheet.csv ]] ; then
    echo 'Miso generated SampleSheet.csv missing, hence aborting.'
    echo 'Place SampleSheet.csv in the working directory'
    exit
fi

#Defining environment variables for file input
fileconv=SampleSheet.csv
filein=index2_barcodes.fasta
fileout=index2_reverse.fasta
infasta=in_fasta
outfasta=out_fasta


#Swapping the first and second column name, but keeping the same header value. This step not needed now, as we are generating directly from MISO mysql database
#awk -F, ' { t = $1; $1 = $2; $2 = t; print; } '  $fileorig | sed "s/\(Sample_Name\) \(Sample_ID\)/\2 \1/" | sed  -e 's/\s\+/,/g' | sed  's/^,//g' | sed  '/^$/d' | sed -e '2 s/^\([^,]*\),\([^,]*\)\(.*\)$/\2,\1\3/'  > $fileconv


#Defining if condition if second argument matches
if [[ "$1" =~ [Yy][Ee][Ss] ]]; then

#Processing the input file index2_barcodes.fasta
#cat $fileconv
pre=$(cat $fileconv | awk -F "," '{print $NF}' | sed '1,/index2/d' | sed '/^[[:blank:]]*$/d')

#Output of fasta barcodes
cat $fileconv | awk -F "," '{print $NF}' | sed '1,/index2/d' | sed '/^[[:blank:]]*$/d' > in_fasta

#convert index2_barcodes.fasta  to an array without numeric values
prear=($pre)

#lets declare new increment variable which is preinc=0. Below excecution creates input file as index2_barcodes.fasta format
preinc=0
for i in ${prear[@]};do preinc=$((preinc+1)); echo ">"$preinc;echo $i;done > $filein

#Let's begin with the conversion, loading the necessary module
module load gencore
module load gencore_dev
fastx_reverse_complement -i $filein -o $fileout

#Here I'm skipping the convertion command before this we need to load two modules
post=$(cat $fileout|grep -v '^>[0-9]')

#Output of fasta reverse
cat $fileout|grep -v '^>[0-9]' > out_fasta

#Below GNU awk do the search and replace pattern based on two files in_fast and out_fasta
gawk -i inplace  '
  BEGIN {FS = OFS = ","}
  ARGIND == 1 {f1[FNR] = $1; next}
  ARGIND == 2 {map[f1[FNR]] = $1; next}

  BEGINFILE {start = 0; header = 1}
  start {if (header) {header = 0} else {$NF = map[$NF]}}
  {print}
  $1 == "[Data]" {start = 1}
  ' in_fasta out_fasta SampleSheet.csv

#Removing unncessary files
rm $filein
rm $fileout
rm $infasta
rm $outfasta
echo "OUTPUT with reverse complement can be found here $fileconv"
elif  [[ "$1" =~ [NnOo] ]]; then
echo "OUTPUT without reverse complement can be found here $fileconv."
else
echo ""
fi

####************** Script ends ***************####
