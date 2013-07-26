#!/usr/bin/env python

#Aloft is now compatible with python 2.7+ and python 3
#In order to keep compatibility, make sure to:
#do print("spam") not print "spam" since print is now a function
#do str(5) not `5` since backticks have been removed
#use // for floor division (aka integer division). 5/2 is 2.5 in python3 but 5/2 is 2 in python2 while 5//2 is 2 in both and float(5) / 2 is 2.5 in both.
#convert from binary to strings when necessary (like output from a pipe); opening files intended for binary access requires passing 'b' in file mode
#do not use xrange since it is removed
#consider that some functions (e.g, range, dict.items()) return iterators instead of lists, use list() to convert them to lists if needed
#test aloft with both python3 and python2.7
#see http://docs.python.org/3.0/whatsnew/3.0.html

import sys, os, re, string, array, datetime
from optparse import OptionParser
from subprocess import Popen, PIPE
from vat_run import *
from sequencing import *
from common import *
import argparse
import networkx as nx
import pickle

VERBOSE = None

def abortIfPathDoesNotExist(path, shouldShowHelp=False):
    if path is not None and not os.path.exists(path):
        if shouldShowHelp:
            parser.print_help()
        printError("%s does not exist" % (path))

def abortIfCannotCreateDirectory(directory):
    if not os.path.exists(directory):
        try:
            os.mkdir(directory)
        except:
            parser.print_help()
            printError("Failed to create directory %s" % (directory))

def abortIfCannotWriteFile(filepath):
    try:
        newFile=open(filepath, 'w')
    except:
        parser.print_help()
        printError("%s could not be written to" % (filepath))
    return newFile

def parseCommandLineArguments():
    parser = argparse.ArgumentParser(description='Run aloft predictions. You must at least provide a VCF (via --vcf) or VAT (via --vat) input file. If you provide a VCF file, it will be ran through VAT and then through aloft. If you provide a VAT file instead, it must be sorted numerically (use vcf_sort.py for this).', formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    parser.add_argument('--vcf', help='Path to VCF input file. This can be a compressed .gz file. If not specified, then --vat must be specified.')
    parser.add_argument('--vat', help='Path to VAT input file. If not specified, then --vcf must be specified. This file must be sorted numerically.')

    parser.add_argument('--annotation_interval', help='Path to annotation interval file for VAT', default='data/gencode.v16.pc.interval')
    parser.add_argument('--annotation_sequence', help='Path to annotation sequence file for VAT', default='data/gencode.v16.pc.fa')
    parser.add_argument('--genome', help='Path to directory containing chr*.fa files', default='data/genome/')
    
    parser.add_argument('--output', help='Path to output directory; directory is created if it does not exist', default='aloft_output/')

    parser.add_argument('--cache', help='Output to directory for cached files; directory is created if it does not exist', default='cache/')

    parser.add_argument('--nmd_threshold', help='Distance from premature stop to last exon-exon junction; used to find NMD cause', type=int, default=50)

    parser.add_argument('--verbose', '-v', help='Verbose mode', action='store_true')

    parser.add_argument('--ensembl_table', help='Path to transcript to protein lookup table file', default='data/ens67_gtpcgtpolymorphic.txt')
    parser.add_argument('--protein_features', help='Path to directory containing chr*.prot-features-ens70.txt files', default='data/prot-features/')
    parser.add_argument('--phosphorylation', help='Path to directory containing ptm.phosphorylation.chr*.txt files', default='data/ptm')
    parser.add_argument('--transmembrane', help='Path to directory containing transmembrane chr*.tmsigpcoilslc.ens70.txt', default='data/tm_ens70/')

    parser.add_argument('--thousandG', help='Path to 1000G file', default='data/ALL.wgs.phase1_release_v3.20101123.snps_indels_sv.sites.gencode16.SNPS.vat.vcf')

    parser.add_argument('--haplo_score', help='Path to haploinsufficiency disease scores', default='data/imputed.hi.scores')

    parser.add_argument('--ppi', help='Path to protein-protein interaction network file', default='data/BIOGRID-ORGANISM-Homo_sapiens-3.2.95.tab.txt')
    parser.add_argument('--dominant_genes', help='Path to list of dominant genes', default='data/dominantonly.list')
    parser.add_argument('--recessive_genes', help='Path to list of recessive genes', default='data/science_lofpaper_omim_recessive_filtered.list')

    parser.add_argument('--rates', help='Path to directory containing chr*.maf.rates files', default='data/bases/')
    parser.add_argument('--elements', help='Path to directory containing hg19_chr*_elems.txt files', default='data/elements/')

    parser.add_argument('--dNdS', help='Path to dNdS file', default='data/dNdS_avgs.txt')
    parser.add_argument('--paralogs', help='Path to paralogs file', default='data/within_species_geneparalogs.ens70')
    parser.add_argument('--LOF_score', help='Path to LOF disease scores', default='data/prob_recessive_disease_scores.txt')
    parser.add_argument('--ancestor', help='Path to directory containing homo_sapiens_ancestor_*.fa files', default='data/homo_sapiens_ancestor_GRCh37_e71/')
    parser.add_argument('--netSNP_score', help='Path to netSNP disease scores', default='data/Supplementary_Table8.20Jul2012.txt')
    parser.add_argument('--segdup', help='Path to segdup annotation file', default='data/hg19-segdup.txt')
    parser.add_argument('--annotation', help='Path to .gtf annotation file', default='data/gencode.v16.annotation.gtf')
    parser.add_argument('--exomes', help='Path to directory containing ESP6500.chr*.snps.vcf files', default='data/ESP6500/')
    parser.add_argument('--pseudogenes', help='Path to pseudogenes file', default='data/gencode.v7.pgene.parents')
    parser.add_argument('--disopred_sequences', help='Path to disorder prediction sequences', default='data/disopred_sequences')

    args = parser.parse_args()

    global VERBOSE
    VERBOSE = args.verbose

    #safe way to test if args has an attribute named arg whose name is equal to key
    def testArgumentEquality(args, arg, key):
        if not hasattr(args, key):
            raise Exception("%s attribute does not exist!" % (key))
        return key == arg

    #Expand ~ to user's home directory for all argument paths
    for arg, path in vars(args).items():
        if path is not None and not any(map(lambda key: testArgumentEquality(args, arg, key), ['nmd_threshold', 'verbose'])):
            setattr(args, arg, os.path.expanduser(path))

    if not args.vcf and not args.vat:
        parser.print_help()
        printError("Neither a VCF or VAT file was specified. You must supply one of these as your input file")

    if args.vcf and args.vat:
        parser.print_help()
        printError("Both a VCF or VAT file were specified. You must supply only one of these as your input file, but not both")

    abortIfPathDoesNotExist(args.vat)
    abortIfPathDoesNotExist(args.vcf)

    abortIfCannotCreateDirectory(args.output)
    abortIfCannotCreateDirectory(args.cache)

    abortIfCannotCreateDirectory(os.path.join(args.cache, "gerp"))

    #Try to see if we can detect and open all input files
    for arg, path in vars(args).items():
        if not any(map(lambda key: testArgumentEquality(args, arg, key), ['vat', 'vcf', 'output', 'cache', 'nmd_threshold', 'verbose'])):
            abortIfPathDoesNotExist(path, True)
            if not os.path.isdir(path):
                try:
                    f = open(path)
                    f.close()
                except:
                    printError("--%s: %s cannot be opened (insufficient read privileges?)" % (arg, path))
    return args

def getAncestors(ancespath):
    ## Coordinates for chromosomes are 1-based.
    ancestor={}
    for i in chrs:
        individualAncestorPath = os.path.join(ancespath, 'homo_sapiens_ancestor_'+i+'.fa')
        try:
            f=open(individualAncestorPath)
        except:
            printError("%s could not be opened... Exiting program" % (individualAncestorPath))

        if VERBOSE: print('Reading ancestral chromosome '+i+'...')
        f.readline()    ##first >**** line
        ancestor[i] = '0' + f.read().replace("\n", "")
        f.close()
    return ancestor

def parseances(ancestor, line):
    if line.startswith("#") or line=="\n":
        return ""
    data = line.split('\t')
    chr_num = data[0].split('chr')[-1]
    start = int(data[1])
    return ancestor[chr_num][start:start+len(data[3])].upper()

def getGERPData(vatFile, chrs, GERPelementpath, GERPratepath, GERPratecachepath, codingExonIntervals):
    ## Coordinates are 1-based.
    ## All GERP intervals include endpoints
    GERPratedata=[]
    GERPelementdata=[]
    GERPrejectiondata = []
    exonsCountData = []

    vatFile.seek(0)
    line = vatFile.readline()
    while line.startswith("#") or line=="\n":
        GERPratedata.append('')
        GERPelementdata.append('')
        GERPrejectiondata.append('')
        exonsCountData.append('')
        line=vatFile.readline()

    for i in chrs:
        if line.split('\t')[0].split('chr')[-1]!=i:
            if VERBOSE: print('no indels on chromosome ' + i)
            continue

        individualElementPath = os.path.join(args.elements, 'hg19_chr'+i+'_elems.txt')
        try:
            elementfile=open(individualElementPath)
        except:
            printError("%s could not be opened.." % (individualElementPath))
        
        if VERBOSE:
            print('Reading GERP information for chromosome '+i+'...')
            startTime = datetime.datetime.now()
        
        gerpCacheFile = buildGerpRates(GERPratepath, GERPratecachepath, i)
        
        if VERBOSE: print(str((datetime.datetime.now() - startTime).seconds) + " seconds.")
        
        GERPelements = getGERPelements(elementfile)

        if VERBOSE:
            print('Calculating GERP scores for chromosome '+i+'...')
            startTime = datetime.datetime.now()

        while line.split('\t')[0].split('chr')[-1]==i:
            data = line.split('\t')
            chr_num = data[0].split('chr')[-1]
            start = int(data[1])
            length = len(data[3])
            end = start + length-1  ##inclusive endpoint

            variantIndex = line.index("VA=") + len("VA=")
            variants = line[variantIndex:].split(",")
            variant = variants[0].split(":")
            direction = variant[3]
            transcript = variant[7]

            GERPratedata.append(str(getGerpScore(gerpCacheFile, start, length)))

            exons = codingExonIntervals[chr_num][transcript] if transcript in codingExonIntervals[chr_num] else None
            truncatedExons = getTruncatedExons(exons, transcript, chr_num, start, direction) if exons else None

            exonsCountData.append(":".join([str(len(truncatedExons)) if truncatedExons else ".", str(len(exons)) if exons else "."]))

            elementIndex = findGERPelementIndex(GERPelements, start, end)
            if elementIndex == -1:
                GERPelementdata.append(".")
                GERPrejectiondata.append(".")
            else:
                GERPelementdata.append(str(GERPelements[elementIndex]))

                rejectedElements = []
                if exons and truncatedExons and ('prematureStop' in line or 'insertionFS' in line or 'deletionFS' in line):
                    rejectedElements = getRejectionElementIntersectionData(exons, truncatedExons, GERPelements, elementIndex, direction)

                if len(rejectedElements) > 0:
                    GERPrejectiondata.append(",".join(["%d/%.2f/%d/%d/%.2f" % rejectedElement for rejectedElement in rejectedElements]))
                else:
                    GERPrejectiondata.append(".")
            
            line=vatFile.readline()
        
        if VERBOSE: print(str((datetime.datetime.now() - startTime).seconds) + " seconds.")
        
    return GERPratedata, GERPelementdata, GERPrejectiondata, exonsCountData

def getSegDupData(vatFile, segdupPath, chrs):
    segdups={}
    segdupmax={}
    for i in chrs:
        segdups[i] = []
        segdupmax[i] = []
    if VERBOSE: print("Reading segdup information...")
    segdupfile = open(segdupPath)
    line = segdupfile.readline()
    while line.startswith("#") or line=="\n":
        line=segdupfile.readline()
    while line!="":
        data = line.split('\t')
        chr_num = data[0].split('chr')[-1]
        if '_' in chr_num:
            line = segdupfile.readline()
            continue
        segdups[chr_num].append((int(data[1]),int(data[2])))
        line = segdupfile.readline()
    for i in chrs:
        segdups[i] = sorted(segdups[i])
        maxsofar = 0
        for interval in segdups[i]:
            maxsofar = max(interval[1], maxsofar)
            segdupmax[i].append(maxsofar)
    segdupdata=[]
    vatFile.seek(0)
    line = vatFile.readline()
    while line.startswith("#") or line=="\n":
        segdupdata.append('')
        line=vatFile.readline()
    if VERBOSE: print('Calculating segdup overlaps...')
    while line!="":
        data = line.split('\t')
        chr_num = data[0].split('chr')[-1]
        start = int(data[1])
        length = len(data[3])
        end = start + length-1  ##inclusive endpoint

        ##find right endpoint of interval search 
        low = 0; high = len(segdups[chr_num])-1
        while low<=high:
            mid = (low+high)//2
            if end<segdups[chr_num][mid][0]:
                high = mid-1
            elif mid == len(segdups[chr_num])-1 or end<segdups[chr_num][mid+1][0]:
                break
            else:
                low = mid+1
        right = mid
            
        ##find left endpoint of interval search
        low = 0; high = len(segdups[chr_num])-1
        while low<=high:
            mid = (low+high)//2
            if start>segdups[chr_num][mid][1] and start>segdupmax[chr_num][mid]:
                low = mid+1
            elif mid==0:
                break
            elif start>segdups[chr_num][mid-1][1] and start>segdupmax[chr_num][mid-1]:
                break
            else:
                high = mid-1
        left = mid
        
        overlaps = []
        for interval in segdups[chr_num][left:right+1]:
            ##compare bigger of left enpoints to smaller of right endpoints
            if max(start, interval[0]) <= min(end, interval[1]):
                overlaps.append(interval)
        segdupdata.append(str(overlaps))

        line = vatFile.readline()

    segdupfile.close()
    return segdupdata

#Returns a Pfam vcf-formatted description, and a verbose description
#The vcf-formatted description is in format Pfam_ID:domain_length:max_domain_percent_lost:number_pfams_in_domain:number_pfams_in_truncation
#The verbose description returned is a) a series of concatenated Pfam_ID:domain_length:percent_lost, and a series of concatenated domain_id_lost:domain_length 
##domain value=amino acid coordinate of premature stop
def getPfamDescription(transcriptToProteinHash, chromosome, transcriptID, domainValue, chromosomesPFam, domainType):
    pfamsMatched = []
    maxPercentageLostPfamIndex = -1
    pfamDescription = ""
    pfamVerboseDescription = None

    chromosomesPFam = chromosomesPFam[domainType]

    if transcriptID in transcriptToProteinHash and transcriptToProteinHash[transcriptID] in chromosomesPFam[chromosome]:
        pfamComponentsList = chromosomesPFam[chromosome][transcriptToProteinHash[transcriptID]]
        domainsLost = ""
        numberOfDomainsLost = 0
        for pfamComponents in pfamComponentsList:
            domainComponents = pfamComponents[1].split("-")
            domainStart = int(domainComponents[0])
            domainEnd = int(domainComponents[1])
            domainLength = domainEnd - domainStart + 1
            if domainValue >= domainStart and domainValue <= domainEnd:
                domainLengthLost = domainEnd - domainValue + 1
                domainPercentLost = domainLengthLost * 100.0 / domainLength

                if not pfamVerboseDescription:
                    pfamVerboseDescription = ""

                pfamVerboseDescription += ":%s:%d:%.2f" % (pfamComponents[0], domainLength, domainPercentLost)

                #Find largest percentage lost pfam
                if maxPercentageLostPfamIndex < 0 or domainPercentLost > float(pfamsMatched[maxPercentageLostPfamIndex].split(":")[3]):
                    maxPercentageLostPfamIndex = len(pfamsMatched)

                pfamsMatched.append(":%s:%d:%.2f" % (pfamComponents[0], domainLength, domainPercentLost))

            elif domainValue < domainStart:
                domainsLost += ":" + pfamComponents[0] + ":" + str(domainLength)
                numberOfDomainsLost += 1

        if maxPercentageLostPfamIndex >= 0:
            pfamDescription = pfamsMatched[maxPercentageLostPfamIndex] + ":" + str(len(pfamsMatched))

        if pfamDescription == "":
            pfamDescription = ":NO_"+domainType+":NA:NA:0"
            pfamVerboseDescription = "NO_"+domainType

        verboseDomainsLost = str(domainsLost)
        if verboseDomainsLost.startswith(":"):
            verboseDomainsLost = verboseDomainsLost[1:]

        if verboseDomainsLost == "":
            verboseDomainsLost = "NO_"+domainType

        if pfamVerboseDescription.startswith(":"):
            #Remove beginning colon
            pfamVerboseDescription = pfamVerboseDescription[1:]

        pfamVerboseDescription = [pfamVerboseDescription, verboseDomainsLost]

        #Add number of domains lost
        pfamDescription += ":" + str(numberOfDomainsLost)

    #If no ENST or ENSP ID could be matched
    if pfamDescription == "":
        pfamDescription = ":NO_"+domainType+":NA:NA:0:0"
    if pfamVerboseDescription is None:
        pfamVerboseDescription = ["NO_"+domainType, "NO_"+domainType]

    return pfamDescription, pfamVerboseDescription
        
# Get a mapping of Transcript ID's (ENST) -> Proteins ID's (ENSP)
def getTranscriptToProteinHash(transcriptToProteinFilePath):
    try:
        inputFile = open(transcriptToProteinFilePath, "r")
    except:
        printError("Failed to open %s" % (transcriptToProteinFilePath))

    transcriptToProteinHash = {}
    firstLine = True
    for line in inputFile:
        if firstLine:
            firstLine = False
        else:
            components = line.split('\t')
            if components[1].strip() and components[2].strip():
                transcriptToProteinHash[components[1]] = components[2]

    inputFile.close()
    return transcriptToProteinHash

def getChromosomesPfamTable(chrs, pfamDirectory, strformat, domainTypeList, domainTypeColumn=0):
   # Get a mapping of Protein ID's -> Pfam information, for each chromosome
    chromosomesPFam = {i:{} for i in domainTypeList}
    for chromosome in chrs:
        for domainType in domainTypeList:
            chromosomesPFam[domainType][chromosome] = {}
        path = os.path.join(pfamDirectory, strformat % (chromosome))

        #Get rid of duplicate lines
        try:
            pipe1 = Popen(['sort', path], stdout=PIPE)
            pipe2 = Popen(['uniq'], stdin=pipe1.stdout, stdout=PIPE)
            inputFile = pipe2.stdout
        except:
            printError("Couldn't read %s, skipping %s" % (path, chromosome), False)
            continue

        linesToSkip = 2
        for lineBytes in inputFile:
            line = lineBytes.decode()
            if linesToSkip > 0:
                linesToSkip -= 1
            else:
                components = line.split("\t")
                digitmatch = re.search("\d", components[domainTypeColumn])
                if not digitmatch:
                    domainType = components[domainTypeColumn].strip()
                else:
                    domainType = components[domainTypeColumn][:digitmatch.start()]
                if domainType not in domainTypeList:
                    continue
                if len(components) >= 3:
                    translationID = components[2].replace('(', '').replace(')', '').strip()
                    if translationID in chromosomesPFam[domainType][chromosome]:
                        chromosomesPFam[domainType][chromosome][translationID].append(components)
                    else:
                        chromosomesPFam[domainType][chromosome][translationID] = [components]

        inputFile.close()

    return chromosomesPFam

def getGenomeSequences(genomePath, chromosome):
    individualSequencePath = os.path.join(genomePath, "chr%s.fa" % (chromosome))
    try:
        f=open(individualSequencePath)
    except:
        printError("%s could not be opened" % (individualSequencePath))

    if VERBOSE: print("Reading genome sequences for chromosome %s..." % (chromosome))

    f.readline()    ##first >chr* line
    genomeSequences = '0' + f.read().replace("\n", "")
    f.close()

    return genomeSequences

def getCDSAndExonDictionaries(annotationPath, chrs):
    CDS={}; exon={}; stop_codon={}  ##{chr_num: {transcript: [(a,b),(c,d)..] } }
    transcript_strand={}            ##{transcript_id:+ or -}
    for chr_num in chrs:
        CDS[chr_num]={}
        exon[chr_num]={}
        stop_codon[chr_num]={}
    CDS['M']={}
    exon['M']={}
    stop_codon['M']={}

    ##count number of lines preceding actual annotation data
    counter = 0
    annotfile = open(annotationPath)
    for line in annotfile:
        if len(line)<3:
            counter+=1
            continue
        if line.startswith("#"):    ##all preceding lines begin with #
            counter+=1
        else:
            annotfile.seek(0)
            break
    for i in range(0,counter):
        annotfile.readline()

    ##begin going through actual annotation data
    oldtr = ""  ##last seen transcript
    oldchr = "" ##chr num of last seen transcript
    tlines = [] ##all split CDS lines in oldtr
    for line in annotfile:
        data = line.strip().split('\t')
        chr_num=data[0].split('chr')[-1]
        annottype = data[2]
        
        if annottype!='exon' and annottype!='transcript' and annottype!='CDS' and annottype!='stop_codon':
            continue
        if annottype=='transcript':
            transcript = data[8].split(';')[1].split('"')[1]
            transcript_strand[transcript]=data[6]
            if oldtr!="":
                if len(tlines)>0:
                    if transcript_strand[oldtr]=='+':
                        oldsort = sorted(tlines, key=lambda s: int(s[3]))
                        first = oldsort[0]
                        CDS[oldchr][oldtr].append((int(first[3])+int(first[7]), int(first[4])))
                        for CDSline in oldsort[1:]:
                            CDS[oldchr][oldtr].append((int(CDSline[3]),int(CDSline[4])))
                    else:
                        oldsort = sorted(tlines, key=lambda s: int(s[3]), reverse=True)
                        first = oldsort[0]
                        CDS[oldchr][oldtr].append((int(first[3]), int(first[4])-int(first[7])))
                        for CDSline in oldsort[1:]:
                            CDS[oldchr][oldtr].append((int(CDSline[3]),int(CDSline[4])))
            oldtr = transcript
            oldchr = chr_num
            tlines=[]
            exon[chr_num][transcript] = []
            CDS[chr_num][transcript] = []
        else:  ## then is either exon or CDS or stop codon
            begin = int(data[3])
            end = int(data[4])
            if data[2]=='exon':  
                exon[chr_num][transcript].append((begin, end))  ##
            elif data[2]=='CDS':
                tlines.append(data)  ##append data for reanalysis (mRNA_start_NF cases)
            else:  ##stop codon
                stop_codon[chr_num][transcript] = (begin,end)
    if len(tlines)>0:
        if transcript_strand[oldtr]=='+':
            oldsort = sorted(tlines, key=lambda s: int(s[3]))
            first = oldsort[0]
            CDS[oldchr][oldtr].append((int(first[3])+int(first[7]), int(first[4])))
            for CDSline in oldsort[1:]:
                CDS[oldchr][oldtr].append((int(CDSline[3]),int(CDSline[4])))
        else:
            oldsort = sorted(tlines, key=lambda s: int(s[3]), reverse=True)
            first = oldsort[0]
            CDS[oldchr][oldtr].append((int(first[3]), int(first[4])-int(first[7])))
            for CDSline in oldsort[1:]:
                CDS[oldchr][oldtr].append((int(CDSline[3]),int(CDSline[4])))

    annotfile.close()

    return transcript_strand, CDS, exon, stop_codon

def get1000GChromosomeInfo(thousandGPath):
    thousandGChromosomeInfo = {}

    for thousandGLine in open(thousandGPath):
        if not thousandGLine.startswith("#"):
            thousandGLineComponents = thousandGLine.rstrip("\n").split("\t")
            thousandGChromosomeNumber = thousandGLineComponents[0].replace("chr", "")
            if not (thousandGChromosomeNumber in thousandGChromosomeInfo):
                thousandGChromosomeInfo[thousandGChromosomeNumber] = {}
            
            thousandGChromosomeInfo[thousandGChromosomeNumber][int(thousandGLineComponents[1])] = thousandGLineComponents[7]

    return thousandGChromosomeInfo

def getPPINetwork(ppiPath):
    ppi = nx.Graph()
    ppifile = open(ppiPath)
    ppifile.readline()
    for line in ppifile:
        data = line.split('\t')
        ppi.add_edge(data[2], data[3])
    ppifile.close()
    return ppi

#This function assumes the key is the 0'th column
def getScores(filepath, scoreColumnIndex):
    scores = {}
    scorefile = open(filepath)
    scorefile.readline()
    for line in scorefile:
        data = line.strip().split("\t")
        scores[data[0].upper()] = data[scoreColumnIndex]
    scorefile.close()
    return scores

def getPseudogeneData(pseudogenesPath):
    numpseudogenes = {}     ##{parent transcript: # of assoc. pseudogenes}
    pseudogenesfile = open(pseudogenesPath)
    pseudogenesfile.readline()
    for line in pseudogenesfile:
        tx = line.split('\t')[6]
        if tx in numpseudogenes:
            numpseudogenes[tx] = numpseudogenes[tx]+1
        else:
            numpseudogenes[tx] = 1
    pseudogenesfile.close()
    return numpseudogenes

def getParalogData(paralogsPath):
    paralogs = {}     ##{ENSG ID (without . subclassifier): set(assoc. paralogs)}
    paralogsfile = open(paralogsPath)
    paralogsfile.readline()
    for line in paralogsfile:
        id1 = line.split('\t')[0]
        id2 = line.split('\t')[1]
        if id1 not in paralogs:
            paralogs[id1] = set()
        paralogs[id1].add(id2)
        if id2 not in paralogs:
            paralogs[id2] = set()
        paralogs[id2].add(id1)
    paralogsfile.close()
    return paralogs

def getdNdSData(dNdSPath):
    dNdSmacaque = {}      ##{ENST ID (without . subclassifier): dN/dS (STRING)}
    dNdSmouse = {}
    dNdSfile = open(dNdSPath)
    dNdSfile.readline()
    for line in dNdSfile:
        data = line.strip().split('\t')
        tx = data[1]
        dNdSmacaque[tx] = data[2]
        dNdSmouse[tx] = data[3]
    dNdSfile.close()
    return dNdSmacaque, dNdSmouse

def calculateExomeCoordinate(component):
    values = component.split("=")[1].split(",")
    if (int(values[0]) + int(values[1])) == 0:
        return 0.0
    return int(values[0]) * 1.0 / (int(values[0]) + int(values[1]))

def getESP6500ExomeChromosomeInfo(exomesPath, chromosomes):
    exomesChromosomeInfo = {}
    for chromosome in chromosomes:
        exomesChromosomeInfo[chromosome] = {}
        exomePath = os.path.join(exomesPath, 'ESP6500.chr%s.snps.vcf' % (chromosome)) 
        try:
            exomeInputFile = open(exomePath)
        except:
            printError("Couldn't read %s, skipping.." % (exomePath), False)
            exomeInputFile = None
        
        if exomeInputFile:
            for exomeLine in exomeInputFile:
                if not exomeLine.startswith("#"):
                    exomeLineComponents = exomeLine.split("\t")
                    
                    x = "NA"
                    y = "NA"
                    z = "NA"
                    for component in exomeLineComponents[7].split(";"):
                        if component.startswith('EA_AC='):
                            x = "%.4f" % (calculateExomeCoordinate(component))
                        elif component.startswith('AA_AC='):
                            y = "%.4f" % (calculateExomeCoordinate(component))
                        elif component.startswith('TAC='):
                            z = "%.4f" % (calculateExomeCoordinate(component))
                            
                    exomesChromosomeInfo[chromosome][int(exomeLineComponents[1])] = ("%s,%s,%s" % (x, y, z))
            
            exomeInputFile.close()
    return exomesChromosomeInfo

def parsePPI(ppi, ppiHash, hashKey, gene_name, genes):
    dist = None
    if gene_name in ppiHash[hashKey]:
        dist = ppiHash[hashKey][gene_name]
    else:
        for gene in genes:
            if gene != gene_name and gene in ppi and nx.has_path(ppi, gene_name, gene):
                shortestPathLength = nx.shortest_path_length(ppi, gene_name, gene)
                if dist is None:
                    dist = shortestPathLength
                else:
                    dist = min(dist, shortestPathLength)
            ppiHash[hashKey][gene_name] = dist

    numberOfNeighbors = sum(1 for gene in genes if gene != gene_name and gene in ppi.neighbors(gene_name))
    return dist, numberOfNeighbors

def findNMDForIndelsAndPrematureStop(nmdThreshold, chr_num, transcript, exon, stop_codon, genomeSequences):
    nmdHash = {"NMD" : None, 'splice1' : None, 'splice2' : None, 'canonical' : None, 'newCDSpos' : None, 'stopCDS' : None, 'nextATG' : None, 'incrcodingpos' : None, 'issinglecodingexon' : None}

    l = sorted(CDS[chr_num][transcript])
    if len(l)==0:
        return nmdHash
    nmdHash['issinglecodingexon'] = "YES" if len(l)==1 else "NO"
    numberOfExonsHash = sorted(exon[chr_num][transcript])
    CDSseq = ''; exonseq = ''
    CDSprec = []; exonprec = []             ## prec holds # preceding nucleotides
    ispositivestr = transcript_strand[transcript]=='+'
    
    ## build spliced exon and CDS sequences and maintain coordinate wrt transcript
    tot = 0
    for j in range(0,len(l)):
        if ispositivestr:
            i=j
            CDSseq+=genomeSequences[l[i][0]:l[i][1]+1].upper()
        else:
            i=len(l)-j-1
            CDSseq+=compstr(genomeSequences[l[i][0]:l[i][1]+1].upper())
        CDSprec.append(tot)              ## stores in index i
        tot += l[i][1]+1-l[i][0]
    ## add on STOP sequence if annotated
    try:
        s = stop_codon[chr_num][transcript]
    except:
        s=(2,0)
    if ispositivestr:
        CDSseq+=genomeSequences[s[0]:s[1]+1].upper()
    else:
        CDSseq+=compstr(genomeSequences[s[0]:s[1]+1].upper())
    
    tot = 0
    for j in range(0,len(numberOfExonsHash)):
        if ispositivestr:
            i=j
            exonseq+=genomeSequences[numberOfExonsHash[i][0]:numberOfExonsHash[i][1]+1].upper()
        else:
            i=len(numberOfExonsHash)-j-1
            exonseq+=compstr(genomeSequences[numberOfExonsHash[i][0]:numberOfExonsHash[i][1]+1].upper())
        exonprec.append(tot)            ## stores in index i
        tot += numberOfExonsHash[i][1]+1-numberOfExonsHash[i][0]
    
    ##build coding exons IN ORDER OF TRANSLATION, i.e. start->stop
    coding_exons = []           ## flag coding exons (corresponds to exonpos)
    CDS2ex = {}                 ## maps CDSpos to exonpos    
    for i in range(0,len(numberOfExonsHash)):   ## i = exonpos
        k = i if ispositivestr else len(numberOfExonsHash)-i-1  ## k = exonindex
        coding_exons.append(0)
        for j in range(0,len(l)):   ## j = CDSindex
            if l[j][0]>=numberOfExonsHash[k][0] and l[j][1]<=numberOfExonsHash[k][1]:
                coding_exons[i] = 1
                j2 = j if ispositivestr else len(l)-j-1     ## j2 = CDSpos
                CDS2ex[j2]=i
                break
                
    ncodingexons = sum(coding_exons)    ## number of coding exons
    try:
        UTR=len(numberOfExonsHash)-(coding_exons.index(1)+ncodingexons) ## number of 3'UTR exons
    except:     ## no coding exons
        UTR=0
    
    ## find CDS and exon interval numbers
    flag1=0
    flag2=0
    CDSpos=-1        ## this gives the CDSpos 0-based: i.e. first CDS is index 0
    for i in range(0,len(l)):
        if start>=l[i][0] and start<=l[i][1]:
            CDSpos = i if ispositivestr else len(l)-i-1
        if start>=l[i][0] and end<=l[i][1]:
            flag1 = 1   ##indel is completely contained in CDS
            break
    
    exonpos=-1       ## this gives the exonpos also 0-based
    for i in range(0,len(numberOfExonsHash)):
        if start>=numberOfExonsHash[i][0] and start<=numberOfExonsHash[i][1]:
            exonpos = i if ispositivestr else len(numberOfExonsHash)-i-1
        if start>=numberOfExonsHash[i][0] and end<=numberOfExonsHash[i][1]:
            flag2 = 1   ##indel is completely contained in exon
            break
    if CDSpos==-1 or exonpos==-1:   ##start position of indel was not in ANY intervals
        nmdHash['NMD'] = "no exons or no CDS containing start of indel"
        return nmdHash
    
    exonindex= exonpos if ispositivestr else len(numberOfExonsHash)-exonpos-1
    CDSindex= CDSpos if ispositivestr else len(l)-CDSpos-1
    
    codingpos = exonpos-coding_exons.index(1)      ## this gives coding exon position 0-based
    
    diff = len(subst)-len(data[3])
    if ispositivestr:
        ## 1-based position of indel in CDS coordinates
        newCDSpos = CDSprec[CDSpos] + start - l[CDSindex][0] + 1
        ## 1-based position of indel in exon coordinates
        newexonpos = exonprec[exonpos] + start - numberOfExonsHash[exonindex][0] + 1
    else:
        newCDSpos = CDSprec[CDSpos] + l[CDSindex][1] - start + 1
        newexonpos = exonprec[exonpos] + numberOfExonsHash[exonindex][1] - start + 1
    ## # of exon nucleotides before e-e junction
    if newexonpos-1<exonprec[-1]:       ##indel being before last e-e junction shifts e-e position
        juncpos = exonprec[-1]+diff     ##WRONG IF START POSITION IS LAST NUCLEOTIDE BEFORE E-E AND
                                        ##IS DELETION (WOULD BE SPLICE OVERLAP)
    else:                               ##indel is after last junction, position unchanged
        juncpos = exonprec[-1]
    
    nmdHash['newCDSpos'] = newCDSpos
    
    lastindex = -1 if ispositivestr else 0
    indeltoend = exonprec[-1]+numberOfExonsHash[lastindex][1]-numberOfExonsHash[lastindex][0]+1 + diff - (newexonpos-1) ##CHECK THIS EXTRA +1
    if flag1==0:
        nmdHash['NMD'] = "no CDS regions completely containing variant"
        return nmdHash

    if flag2==0:
        nmdHash['NMD'] = "no exon regions completely containing variant"
        return nmdHash
        
    if ispositivestr:
        modCDSseq = CDSseq[0:newCDSpos-1]
        modCDSseq += subst
        modCDSseq += CDSseq[newCDSpos-1+len(data[3]):]
    else:
        modCDSseq = CDSseq[0:newCDSpos-len(data[3])]
        modCDSseq += compstr(subst)
        modCDSseq += CDSseq[newCDSpos:]
    ref_aa = translate_aa(CDSseq)
    alt_aa = translate_aa(modCDSseq)
    
    try:
        nextATG = str(3*(alt_aa[:1].index('M')+1))
    except:
        nextATG = 'N/A'

    nmdHash['nextATG'] = nextATG
    
    ## # of CDS nucleotides before stop codon in alternate sequence
    try:
        stopCDS = 3*alt_aa.index('*')
        nmdHash['stopCDS'] = stopCDS
    except:
        nmdHash['NMD'] = "No stop codon found in alt_aa"
        return nmdHash
    
    ## stopexon is # of exon nucleotides preceding first nucleotide of stop codon
    ## increxon is the exon position (not exon index) where the new stop occurs
    
    ## if is in very last CDS or STOP is in current CDS
    if CDSpos==len(l)-1 or (stopCDS>=CDSprec[CDSpos] and stopCDS<CDSprec[CDSpos+1]+diff):
        increxon = exonpos
        if ispositivestr:
            stopexon = exonprec[exonpos]+l[CDSpos][0]-numberOfExonsHash[exonpos][0]+stopCDS-CDSprec[CDSpos]
        else:
            stopexon = exonprec[exonpos]+numberOfExonsHash[exonindex][1]-l[CDSindex][1]+stopCDS-CDSprec[CDSpos]
    else:
        incrCDS = CDSpos
        while incrCDS<len(l):
            increxon = CDS2ex[incrCDS]
            if incrCDS==len(l)-1 or (stopCDS>=CDSprec[incrCDS]+diff and stopCDS<CDSprec[incrCDS+1]+diff):
                if ispositivestr:
                    stopexon = exonprec[increxon]+l[incrCDS][0]-numberOfExonsHash[increxon][0]+stopCDS-(CDSprec[incrCDS]+diff)
                else:
                    stopexon = exonprec[increxon]+numberOfExonsHash[len(numberOfExonsHash)-increxon-1][1]-l[len(l)-incrCDS-1][1]+stopCDS-(CDSprec[incrCDS]+diff)
                break
            incrCDS+=1
    incrcoding = sum(coding_exons[:increxon])   ##incrcoding is the coding exon position where new stop occurs
    if ncodingexons == 1:
        incrcodingpos = 'single'
    elif incrcoding==0:
        incrcodingpos = 'first'
    elif incrcoding==ncodingexons-1:
        incrcodingpos = 'last'
    else:
        incrcodingpos = 'middle'

    nmdHash['incrcodingpos'] = incrcodingpos
    
    ## distances are calculated as follows: TAG_ _| is 5 from exon-exon junction/end of transcript etc.
    ## end of transcript is denoted as end of last exon.
    
    ##number of nucleotides in all exons
    transcriptend = exonprec[-1]+numberOfExonsHash[lastindex][1]-numberOfExonsHash[lastindex][0]+1 + diff    ## in exon coordinates
    stoptoend = transcriptend - stopexon
    stoptojunc = juncpos - stopexon
    indeltoend = transcriptend - (newexonpos-1)
    nmdHash['NMD'] = 'YES' if stoptojunc >= nmdThreshold else 'NO'
    
    ##exon index where new stop occurs
    increxonindex = increxon if ispositivestr else len(numberOfExonsHash)-increxon-1
    
    if increxon==0:
        splice1='.'     ## 5' flanking splice site (acceptor)
    else:
        if ispositivestr:
            splice1=genomeSequences[numberOfExonsHash[increxonindex][0]-2:numberOfExonsHash[increxonindex][0]].upper()
        else:
            splice1=compstr(genomeSequences[numberOfExonsHash[increxonindex][1]+1:numberOfExonsHash[increxonindex][1]+3].upper())                
    if increxon==len(numberOfExonsHash)-1:
        splice2='.'     ## 3' flanking splice site (donor)
    else:
        if ispositivestr:
            splice2=genomeSequences[numberOfExonsHash[increxon][1]+1:numberOfExonsHash[increxon][1]+3].upper()
        else:
            splice2=compstr(genomeSequences[numberOfExonsHash[increxonindex][0]-2:numberOfExonsHash[increxonindex][0]].upper())
        
    canonical = (splice1=='AG' or splice1=='.') and (splice2=='GT' or splice2=='.')
    canonical = 'YES' if canonical else 'NO'

    nmdHash['splice1'] = splice1
    nmdHash['splice2'] = splice2
    nmdHash['canonical'] = canonical

    return nmdHash

#not exactly sure what this function does so not exactly sure what to call it
def searchInSplices(chr_num, transcript, genomeSequences, ispositivestr, start):
    newData = {'found' : None, 'new' : None, 'acceptor' : None, 'donor' : None, 'intronlength' : None}
    l = sorted(CDS[chr_num][transcript], reverse= not ispositivestr)
    found = False
    end = 0  ##0 for end toward smaller basepair number, 1 for other end
    for i in range(0,len(l)):
        r = l[i]
        if start-r[1] in [1,2]:
            end = 1
            found = True
            break
        elif r[0]-start in [1,2]:
            end = 0
            found = True
            break

    newData['found'] = found
    if not found:
        spliceOutputFile.write('\t'+'\t'.join(outdata[i] for i in ["shortest path to recessive gene", "recessive neighbors"]))
        spliceOutputFile.write("\tCDS match not found: pos="+str(start)+' transcript='+transcript+'\n')
        return newData

    if ispositivestr:
        if (end==0 and i==0) or (end==1 and i==len(l)-1):
            return newData
        if end==0:
            acceptor = genomeSequences[l[i][0]-2:l[i][0]].upper()
            if start==l[i][0]-2:
                new = (1, subst+acceptor[1])
            else:
                new = (1, acceptor[0]+subst)
            donor = genomeSequences[l[i-1][1]+1:l[i-1][1]+3].upper()
            intronlength = l[i][0]-l[i-1][1]-1
        elif end==1:
            acceptor = genomeSequences[l[i+1][0]-2:l[i+1][0]].upper()
            donor = genomeSequences[l[i][1]+1:l[i][1]+3].upper()
            if start==l[i][1]+1:
                new = (0, subst+donor[1])
            else:
                new = (0, donor[0]+subst)
            intronlength = l[i+1][0]-l[i][1]-1
    else:   ##not ispositivestr
        if (end==1 and i==0) or (end==0 and i==len(l)-1):
            return newData
        if end==0:
            donor = genomeSequences[l[i][0]-2:l[i][0]].upper()
            acceptor = genomeSequences[l[i+1][1]+1:l[i+1][1]+3].upper()
            if start==l[i][0]-2:
                new = (0, subst+donor[1])
            else:
                new = (0, donor[0]+subst)
            intronlength = l[i][0]-l[i+1][1]-1
        elif end==1:
            donor = genomeSequences[l[i-1][0]-2:l[i-1][0]].upper()
            acceptor = genomeSequences[l[i][1]+1:l[i][1]+3].upper()
            if start==l[i][1]+1:
                new = (1, subst+acceptor[1])
            else:
                new = (1, acceptor[0]+subst)
            intronlength = l[i-1][0]-l[i][1]-1
        donor = compstr(donor.upper())
        acceptor = compstr(acceptor.upper())
        new = (new[0],compstr(new[1].upper()))

    newData['donor'] = donor
    newData['acceptor'] = acceptor
    newData['new'] = new
    newData['intronlength'] = intronlength

    return newData

def getMatchingNagnagnagPositions(genomeSequence, start):
    #NAGN <snp>AG NAG
    nagnagSequence = genomeSequences[start-4:start+5]
    if not ispositivestr:
        nagnagSequence = compstr(nagnagSequence)

    nagNagPositions = []

    if nagnagSequence[1:3] == 'AG':
        if ispositivestr:
            nagNagPositions.append(start-3)
        else:
            nagNagPositions.append(start+3)
    
    if nagnagSequence[7:9] == 'AG':
        if ispositivestr:
            nagNagPositions.append(start+3)
        else:
            nagNagPositions.append(start-3)

    return nagNagPositions

if __name__ == "__main__":
    startProgramExecutionTime = datetime.datetime.now()

    args = parseCommandLineArguments()

    if args.vcf:
        #run VAT
        vatPath = os.path.join(args.output, os.path.basename(args.vcf) + ".vat")
        run_vat([sys.argv[0], args.vcf, vatPath, args.annotation_interval, args.annotation_sequence], VERBOSE)
    else:
        vatPath = args.vat
    
    if VERBOSE: print("Running ALoFT on %s" % (vatPath) + "\n")
    
    try:
        vatFile = open(vatPath)
    except:
        printError("Failed to read %s" % (vatPath))
    
    tabbedOutputLofPath = os.path.join(args.output, os.path.basename(vatPath) + ".tabbed_output_lof")
    tabbedOutputSplicePath = os.path.join(args.output, os.path.basename(vatPath) + ".tabbed_output_splice")
    vcfOutputPath = os.path.join(args.output, os.path.basename(vatPath) + ".output.vcf")

    lofOutputFile = abortIfCannotWriteFile(tabbedOutputLofPath)
    spliceOutputFile = abortIfCannotWriteFile(tabbedOutputSplicePath)
    vcfOutputFile = abortIfCannotWriteFile(vcfOutputPath)
    
    chrs = [str(i) for i in range(1, 23)] + ['X', 'Y']
    
    ##list of ancestral alleles for each line in input file,
    ##"" if metadata line, '.' if none available
    ancestors = getAncestors(args.ancestor)
    ancesdata = [parseances(ancestors, line) for line in vatFile]
    del ancestors
    
    #Load exon intervals from .interval file, used later for intersecting with gerp elements
    codingExonIntervals = getCodingExonIntervals(args.annotation_interval)
    
    GERPratedata, GERPelementdata, GERPrejectiondata, exonsCountData = getGERPData(vatFile, chrs, args.elements, args.rates, os.path.join(args.cache, "gerp"), codingExonIntervals)
    segdupdata = getSegDupData(vatFile, args.segdup, chrs)
    
    if VERBOSE:
        print('Building CDS and exon dictionaries...')
        startTime = datetime.datetime.now()
    
    transcript_strand, CDS, exon, stop_codon = getCDSAndExonDictionaries(args.annotation, chrs)
    
    if VERBOSE:
        print(str((datetime.datetime.now() - startTime).seconds) + " seconds.")
        print('Begin ALoFT Calculations and Write-Out (this may take a while)...')
            
    transcriptToProteinHash = getTranscriptToProteinHash(args.ensembl_table)

    ##{'1':{'ENSP...':'PF...\t4-25\t(ENSP...)'}, '2':{...}, ...}
    chromosomesPFam = dict(list(getChromosomesPfamTable(chrs, args.protein_features, r"chr%s.prot-features-ens70.txt", ["PF", "SSF", "SM"]).items()) + list(getChromosomesPfamTable(chrs, args.phosphorylation, r"ptm.phosphosite.chr%s.txt", ["ACETYLATION", "DI-METHYLATION", "METHYLATION", "MONO-METHYLATION", "O-GlcNAc", "PHOSPHORYLATION", "SUMOYLATION", "TRI-METHYLATION", "UBIQUITINATION"], 3).items()) + list(getChromosomesPfamTable(chrs, args.transmembrane, r"chr%s.tmsigpcoilslc.ens70.txt", ["Tmhmm", "Sigp"]).items()))

    #Scan ESP6500 (exome) fields
    exomesChromosomeInfo = getESP6500ExomeChromosomeInfo(args.exomes, chrs)

    #Scan 1000G file
    if VERBOSE: print("Scanning 1000G file")
    thousandGChromosomeInfo = get1000GChromosomeInfo(args.thousandG)
    
    if VERBOSE: print("Reading PPI network")
    ppi = getPPINetwork(args.ppi)
    ppiHashPath = os.path.join(args.cache, "ppi")

    #ppiHash will contain cached values of shortest paths to genes
    if os.path.exists(ppiHashPath):
        ppiHash = pickle.load(open(ppiHashPath, "rb"))
    else:
        ppiHash = {"dgenes" : {}, "rgenes" : {}}
    
    if VERBOSE: print("Reading recessive genes list")
    rgenes = [line.strip() for line in open(args.recessive_genes)]
    
    if VERBOSE: print("Reading dominant genes list")
    dgenes = [line.strip() for line in open(args.dominant_genes)]
    
    if VERBOSE: print("Reading haploinsufficiency disease genes list")
    haploscores = getScores(args.haplo_score, 1)
    
    if VERBOSE: print("Reading LOF disease scores")
    LOFscores = getScores(args.LOF_score, 1)
    
    if VERBOSE: print("Reading netSNP disease scores")
    netSNPscores = getScores(args.netSNP_score, -1)
    
    if VERBOSE: print("Reading pseudogene data")
    numpseudogenes = getPseudogeneData(args.pseudogenes)
    
    if VERBOSE: print("Reading paralog data")
    paralogs = getParalogData(args.paralogs)
    
    if VERBOSE: print("Reading dNdS data")
    dNdSmacaque, dNdSmouse = getdNdSData(args.dNdS)

    #params for PF, SSF, SM, etc
    #this variable could use a better name since it's not just PFAM, but not sure what to call it
    pfamParams = ["PF", "SSF", "SM", "Tmhmm", "Sigp", "ACETYLATION", "DI-METHYLATION", "METHYLATION", "MONO-METHYLATION", "O-GlcNAc","PHOSPHORYLATION", "SUMOYLATION", "TRI-METHYLATION", "UBIQUITINATION"]

    pfamParamsWithTruncations = sum([[param, param + "truncated"] for param in pfamParams], []) #using sum to flatten the list

    ##list of output parameters for LOF and splice variants
    basicparams = ["gene", "gene_id", "partial/full", "transcript", "transcript length", "longest transcript?"]
    LOFparams = ["shortest path to recessive gene", "recessive neighbors",\
                "shortest path to dominant gene", "dominant neighbors",\
                "is single coding exon?",\
                "indel position in CDS", "stop position in CDS",\
                "causes NMD?", "5' flanking splice site",\
                "3' flanking splice site", "canonical?",\
                "# failed filters", "filters failed",\
                "ancestral allele", "GERP score", "GERP element", "GERP rejection", "exon counts",\
                "segmental duplications", "Disorder prediction"] + pfamParamsWithTruncations +\
                ["1000GPhase1", "1000GPhase1_AF", "1000GPhase1_ASN_AF",\
                "1000GPhase1_AFR_AF", "1000GPhase1_EUR_AF",\
                "ESP6500", "ESP6500_AAF",\
                "haploinsufficiency disease score",\
                "LOF disease score", "netSNP disease score",\
                "# pseudogenes associated to transcript",\
                "# paralogs associated to gene",\
                "dN/dS (macaque)", "dN/dS (mouse)"]
    spliceparams = ["shortest path to recessive gene", "recessive neighbors",\
                "shortest path to dominant gene", "dominant neighbors",\
                "donor", "acceptor",\
                "SNP in canonical site?", "other splice site canonical?",\
                "SNP location", "alt donor", "alt acceptor", "nagnag positions",\
                "intron length", "# failed filters", "filters failed",\
                "GERP score", "GERP element", "GERP rejection", "exon counts",\
                "segmental duplications", "1000GPhase1", "1000GPhase1_AF", "1000GPhase1_ASN_AF",\
                "1000GPhase1_AFR_AF", "1000GPhase1_EUR_AF",\
                "ESP6500", "ESP6500_AAF",\
                "haploinsufficiency disease score",\
                "LOF disease score", "netSNP disease score",\
                "# pseudogenes associated to transcript",\
                "# paralogs associated to gene",\
                "dN/dS (macaque)", "dN/dS (mouse)"]
    outdata = {i : "" for i in set(basicparams) | set(LOFparams) | set(spliceparams)}

    lofOutputFile.write('chr\tpos\trsID\tref\talt\tscore\tPASS?\tdetails\t')
    lofOutputFile.write('\t'.join(i for i in basicparams)+'\t')
    lofOutputFile.write('\t'.join(i for i in LOFparams)+'\n')
    
    spliceOutputFile.write('chr\tpos\trsID\tref\talt\tscore\tPASS?\tdetails\t')
    spliceOutputFile.write('\t'.join(i for i in basicparams)+'\t')
    spliceOutputFile.write('\t'.join(i for i in spliceparams)+'\n')

    ##scan through VCF file metadata
    counter = 0
    vatFile.seek(0)
    line = vatFile.readline()
    while line=="\n" or line.startswith("#"):
        vcfOutputFile.write(line)
        counter+=1
        line = vatFile.readline()

    currentLoadedChromosome = None

    while line!="":
        data = line.strip().split('\t')
        chr_num = data[0].split("chr")[-1]
        start = int(data[1])
        end = start+len(data[3])-1

        if not currentLoadedChromosome or currentLoadedChromosome != chr_num:
            genomeSequences = getGenomeSequences(args.genome, chr_num)
            currentLoadedChromosome = chr_num
        
        #Filter lines
        if "deletionFS" in line or "insertionFS" in line or "premature" in line or "splice" in line:
            if data[3] == ancesdata[counter]:
                ancestral = "Ref"
            elif data[4] == ancesdata[counter]:
                ancestral = "Alt"
            else:
                ancestral = "Neither"
            
            ##screen for variant types here.  skip variant if it is not deletion(N)FS, insertion(N)FS, or premature SNP
            lineinfo = {'AA':'AA='+ancesdata[counter],\
                        'Ancestral':'Ancestral='+ancestral,\
                        'GERPscore':'GERPscore='+GERPratedata[counter],\
                        'GERPelement':'GERPelement='+GERPelementdata[counter],\
                        'GERPrejection':'GERPrejection='+GERPrejectiondata[counter],\
                        'exoncounts':'exoncounts='+exonsCountData[counter],\
                        'SegDup':'SegDup='+str(segdupdata[counter].count('('))}
            infotypes = ['AA', 'Ancestral', 'GERPscore', 'GERPelement', 'GERPrejection', 'SegDup']
    
            outdata["ancestral allele"] = ancesdata[counter]
            outdata["GERP score"] = GERPratedata[counter]
            outdata["GERP element"] = GERPelementdata[counter]
            outdata["GERP rejection"] = GERPrejectiondata[counter]
            outdata["exon counts"] = exonsCountData[counter]
            outdata["segmental duplications"] = '.' if segdupdata[counter].count('(') == '0' else segdupdata[counter]
    
            #Adding 1000G fields
            thousandGTags = ['1000GPhase1_AF', '1000GPhase1_ASN_AF', '1000GPhase1_AFR_AF', '1000GPhase1_EUR_AF']
            thousandGComponents = []
            for thousandGTag in thousandGTags:
                thousandGComponents.append(thousandGTag + "=NA")
            
            if chr_num in thousandGChromosomeInfo and start in thousandGChromosomeInfo[chr_num]:
                for info in thousandGChromosomeInfo[chr_num][start].split(";"):
                    infotype = info.split('=')[0]
                    
                    newComponent = "1000GPhase1_" + info
                    thousandGComponentIndex = -1
                    for findIndex in range(len(thousandGTags)):
                        if infotype == "_range".join(thousandGTags[findIndex].split("_")[1:]):
                            thousandGComponentIndex = findIndex
                            break
                    
                    if thousandGComponentIndex >= 0:
                        thousandGComponents[thousandGComponentIndex] = newComponent
            
            infotypes += ['1000GPhase1'] + thousandGTags
            if chr_num in thousandGChromosomeInfo and start in thousandGChromosomeInfo[chr_num]:
                lineinfo['1000GPhase1'] = '1000GPhase1=Yes'
            else:
                lineinfo['1000GPhase1'] = '1000GPhase1=No'
            
            #Add 1000G entries to output
            for tagIndex in range(len(thousandGTags)):
                lineinfo[thousandGTags[tagIndex]] = thousandGComponents[tagIndex]
            
            #Add exomes info to output
            infotypes += ['ESP6500', 'ESP6500_AAF']
            if start in exomesChromosomeInfo[chr_num]:
                lineinfo['ESP6500'] = 'ESP6500=Yes'
                lineinfo['ESP6500_AAF'] = 'ESP6500_AAF=' + exomesChromosomeInfo[chr_num][start]
            else:
                lineinfo['ESP6500'] = 'ESP6500=No'
                lineinfo['ESP6500_AAF'] = 'ESP6500_AAF=NA,NA,NA'
    
            for tag in ['1000GPhase1'] + thousandGTags + ['ESP6500', 'ESP6500_AAF']:
                outdata[tag] = lineinfo[tag]
            
            dataInfoComponents = data[7].split(';')
            found = 0
            for info in dataInfoComponents:
                infotype = info.split('=')[0]
                if infotype == 'VA':
                    variants = info.split('VA=')[-1].split(',')
                    found = 1
                if infotype!='AA' and infotype!='VA':
                    lineinfo[infotype]=info
                    infotypes.append(infotype)
            
            if found==1:
                lineinfo['VA']='VA='
                infotypes.append('VA')

            def insertAncestralField(outfile):
                ancestralInsertion = ";".join([lineinfo['Ancestral']] + data[7].split(";"))
                outfile.write("\t".join(data[0:7] + [ancestralInsertion] + data[8:]))
                outfile.write('\t'+ '\t'.join(outdata[i] for i in basicparams))
            
            LOFvariants = []
            splicevariants = []
            othervariants = []
            for variant in variants:
                ##alternate allele corresponding to variant
                subst = data[4].split(',')[int(variant.split(':')[0])-1]
                
                if "deletionFS" not in variant and "insertionFS" not in variant:
                    if "premature" not in variant and "splice" not in variant:
                        othervariants.append(variant)
                        continue
                details = variant.split(":")
    
                outdata["gene"], outdata["gene_id"] = details[1], details[2]
    
                if details[5].split("/")[0]==details[5].split("/")[1]:
                    pf = "full"
                else:
                    pf = "partial"
                outdata["partial/full"] = pf
                
                transcripts = []
    
                for i in range(6, len(details)-1, 3):
                    transcripts.append(details[i:i+3])
                longesttranscript = max([int(i[2].split('_')[0]) for i in transcripts])
    
                ##calculate distance to dominant and recessive genes
                gene_name = outdata["gene"]
                if gene_name in ppi:
                    dominantdist, numberOfDominantNeighbors = parsePPI(ppi, ppiHash, "dgenes", gene_name, dgenes)
                    outdata["shortest path to dominant gene"] = 'N/A' if dominantdist is None else str(dominantdist)
                    outdata["dominant neighbors"] = str(numberOfDominantNeighbors)

                    recessdist, numberOfRecessiveNeighbors = parsePPI(ppi, ppiHash, "rgenes", gene_name, rgenes)
                    if recessdist is None and numberOfRecessiveNeighbors > 0:
                        print(gene_name)
                    outdata["shortest path to recessive gene"] = 'N/A' if recessdist is None else str(recessdist)
                    outdata["recessive neighbors"] = str(numberOfRecessiveNeighbors)
                else:
                    outdata["shortest path to recessive gene"] = 'N/A'
                    outdata["recessive neighbors"] = 'N/A'
    
                    outdata["shortest path to dominant gene"] = 'N/A'
                    outdata["dominant neighbors"] = 'N/A'
    
                outdata["haploinsufficiency disease score"] = haploscores[gene_name.upper()] if gene_name.upper() in haploscores else "N/A"
                outdata["LOF disease score"] = LOFscores[gene_name.upper()] if gene_name.upper() in LOFscores else "N/A"
                outdata["netSNP disease score"] = netSNPscores[gene_name.upper()] if gene_name.upper() in netSNPscores else "N/A"
                outdata["# paralogs associated to gene"] = str(len(paralogs[outdata["gene_id"].split('.')[0]])) if outdata["gene_id"].split('.')[0] in paralogs else "0"
    
                ##number of associated pseudogenes computation goes here
    
                if "splice" in variant:
                    ##check that is a SNP splice variant
                    if len(data[3])>1 or len(subst)>1:
                        splicevariants.append(variant)
                        continue
                    splicevariants.append(':'.join(details[:6]))
    
                    for entry in transcripts:
                        splicevariants[-1]+=':' + ':'.join(entry[0:1] + [pf] + entry[1:])
                        transcript = entry[1]
                        outdata["transcript"] = transcript
                        outdata["transcript length"] = entry[2]
                        outdata["longest transcript?"] = "YES" if int(outdata["transcript length"])==longesttranscript else "NO"
                        ispositivestr = transcript_strand[transcript]=='+'

                        nagNagPositions = getMatchingNagnagnagPositions(genomeSequences, start)
                        outdata['nagnag positions'] = '/'.join(map(str, nagNagPositions)) if len(nagNagPositions) > 0 else '.'
    
                        outdata["# pseudogenes associated to transcript"] = str(numpseudogenes[transcript]) if transcript in numpseudogenes else "0"
                        outdata["dN/dS (macaque)"] = dNdSmacaque[transcript.split('.')[0]] if transcript.split('.')[0] in dNdSmacaque else "N/A"
                        outdata["dN/dS (mouse)"] = dNdSmouse[transcript.split('.')[0]] if transcript.split('.')[0] in dNdSmouse else "N/A"
                        
                        insertAncestralField(spliceOutputFile)

                        spliceSearchData = searchInSplices(chr_num, transcript, genomeSequences, ispositivestr, start)

                        def writeSpliceOutput(failure):
                            spliceOutputFile.write('\t'+'\t'.join(outdata[i] for i in ["shortest path to recessive gene", "recessive neighbors"]))
                            spliceOutputFile.write("\t%s: pos=" % (failure) +str(start)+' transcript='+transcript+'\n')

                        if not spliceSearchData['found']:
                            writeSpliceOutput("CDS match not found")
                            continue

                        if not spliceSearchData['new']:
                            writeSpliceOutput("no donor/acceptor pair")
                            continue

                        new = spliceSearchData['new']
                        donor = spliceSearchData['donor']
                        acceptor = spliceSearchData['acceptor']
                        intronlength = spliceSearchData['intronlength']

                        outdata["donor"] = donor
                        outdata["acceptor"] = acceptor
                        outdata["intron length"] = str(intronlength)
                        ##write to output
                        if new[0]==0:
                            isCanonical = 'YES' if donor=='GT' else 'NO'
                            otherCanonical = 'YES' if acceptor=='AG' else 'NO'
                        elif new[0]==1:
                            isCanonical = 'YES' if acceptor=='AG' else 'NO'
                            otherCanonical = 'YES' if donor=='GT' else 'NO'
                        outdata["SNP in canonical site?"] = isCanonical
                        outdata["other splice site canonical?"] = otherCanonical
                        
                        if new[0]==0:
                            outdata["SNP location"] = "donor"
                            outdata["alt donor"] = new[1].upper()
                            outdata["alt acceptor"] = acceptor
                        else:
                            outdata["SNP location"] = "acceptor"
                            outdata["alt donor"] = donor
                            outdata["alt acceptor"] = new[1].upper()
    
    		  #calculation of filters
                        filters_failed = 0
                        failed_filters = []
                        if isCanonical == 'NO':
                            filters_failed = filters_failed+1
                            failed_filters.append('noncanonical')
                        if otherCanonical == 'NO':
                            filters_failed = filters_failed+1
                            failed_filters.append('other_noncanonical')
                        if intronlength < 15:
                            filters_failed = filters_failed+1
                            failed_filters.append('short_intron')
                        if segdupdata[counter].count('(') > 3:
                            filters_failed = filters_failed+1
                            failed_filters.append('heavily_duplicated')
    
                        outdata["# failed filters"] = str(filters_failed)
                        outdata["filters failed"] = ','.join(failed_filters)
    					
    ########################################################
                        spliceOutputFile.write("\t"+"\t".join(outdata[i] for i in spliceparams)+"\n")
    #########################################################
                        splicevariants[-1]+=':'+':'.join([donor+'/'+acceptor, isCanonical, otherCanonical, str(intronlength)])
                        
                else:   ##deletionFS, insertionFS, or prematureStop
                    LOFvariants.append(':'.join(details[:6]))
    
                    for entry in transcripts:
                        LOFvariants[-1]+=':'+':'.join(entry[0:1] + [pf] + entry[1:])
                        
                        tlength = entry[2].split('_')[0]
                        outdata["transcript length"] = tlength
                        try:
                            LOFposition = entry[2].split('_')[1]
                        except:
                            LOFposition = '.'
                        outdata["longest transcript?"] = "YES" if int(tlength)==longesttranscript else "NO"
                        transcript = entry[1]
                        outdata["transcript"]=transcript
                       
    		  #calculation of filters
                        filters_failed = 0
                        failed_filters = []
                        try:	#since LOFposition may not be provided
                            if float(LOFposition)/float(tlength) <= 0.05:
                                filters_failed = filters_failed+1
                                failed_filters.append('near_start')
                            if float(LOFposition)/float(tlength) >= 0.95:
                                filters_failed = filters_failed+1
                                failed_filters.append('near_stop')
                        except:
                            pass
                        if ancesdata[counter]==subst:
                            filters_failed = filters_failed+1
                            failed_filters.append('lof_anc')
                        if segdupdata[counter].count('(') > 3:
                            filters_failed = filters_failed+1
                            failed_filters.append('heavily_duplicated')
                        outdata["# failed filters"] = str(filters_failed)
                        outdata["filters failed"] = ','.join(failed_filters)
    
                        outdata["indel position in CDS"] = "N/A"
                        outdata["stop position in CDS"] = "N/A"
                        outdata["5' flanking splice site"] = "N/A"
                        outdata["3' flanking splice site"] = "N/A"
                        outdata["canonical?"] = "N/A"
                        outdata["# pseudogenes associated to transcript"] = str(numpseudogenes[transcript]) if transcript in numpseudogenes else "0"
                        outdata["dN/dS (macaque)"] = dNdSmacaque[transcript.split('.')[0]] if transcript.split('.')[0] in dNdSmacaque else "N/A"
                        outdata["dN/dS (mouse)"] = dNdSmouse[transcript.split('.')[0]] if transcript.split('.')[0] in dNdSmouse else "N/A"
                        
                        insertAncestralField(lofOutputFile)
                        
                        nmdData = findNMDForIndelsAndPrematureStop(args.nmd_threshold, chr_num, transcript, exon, stop_codon, genomeSequences)

                        if nmdData['NMD'] is None:
                            continue

                        outdata['causes NMD?'] = nmdData['NMD']

                        if nmdData['issinglecodingexon']:
                            outdata["is single coding exon?"] = nmdData['issinglecodingexon']

                        if nmdData['newCDSpos']:
                            outdata['indel position in CDS'] = str(nmdData['newCDSpos'])

                        if nmdData['NMD'] not in ['YES', 'NO']:
                            lofOutputFile.write('\t'+'\t'.join(outdata[i] for i in LOFparams) + '\n')
                            continue

                        lofPosition = nmdData['newCDSpos'] if "prematureStop" in variant else nmdData['stopCDS']

                        outdata["5' flanking splice site"] = nmdData['splice1']
                        outdata["3' flanking splice site"] = nmdData['splice2']
                        outdata["canonical?"] = nmdData['canonical']
                        outdata["stop position in CDS"] = str(lofPosition)

                        vcfPfamDescriptions = {}
                        stopPositionInAminoSpace = int(entry[2].split('_')[2]) if "prematureStop" in variant else (lofPosition - 1) // 3 + 1
                        for paramKey in pfamParams:
                            newDescriptions = getPfamDescription(transcriptToProteinHash, chr_num, transcript.split(".")[0], stopPositionInAminoSpace, chromosomesPFam, paramKey)
                            vcfPfamDescriptions[paramKey] = newDescriptions[0]
                            outdata[paramKey] = newDescriptions[1][0]
                            outdata[pfamParamsWithTruncations[pfamParamsWithTruncations.index(paramKey)+1]] = newDescriptions[1][1]
                        
                        disorderPredictionData = getDisopredData(args.disopred_sequences, transcript, stopPositionInAminoSpace)
                        outdata["Disorder prediction"] = disorderPredictionData

    #########################################################
                        lofOutputFile.write('\t' + '\t'.join(outdata[i] for i in LOFparams)+'\n')
    #########################################################
                            
                        LOFvariants[-1]+=':'+':'.join([nmdData['splice1']+'/'+nmdData['splice2'], str(nmdData['newCDSpos']), str(lofPosition), nmdData['nextATG'], nmdData['NMD'], nmdData['incrcodingpos'], disorderPredictionData]) + ''.join([vcfPfamDescriptions[param] for param in pfamParams])
    
            vcfOutputFile.write('\t'.join(data[k] for k in range(0,7))+'\t')
            allvariants = []
            for variant in LOFvariants:
                allvariants.append(variant)
            for variant in splicevariants:
                allvariants.append(variant)
            for variant in othervariants:
                allvariants.append(variant)
            lineinfo['VA']+=','.join(allvariants) 
            vcfOutputFile.write(';'.join(lineinfo[infotype] for infotype in infotypes)+'\n')
        
        line=vatFile.readline()
        counter+=1
    
    vcfOutputFile.close()
    lofOutputFile.close()
    spliceOutputFile.close()
    vatFile.close()

    #save shortest path values to cache file
    pickle.dump(ppiHash, open(ppiHashPath, "wb"), protocol=2)

    if VERBOSE: print("Finished execution in %d seconds" % ((datetime.datetime.now() - startProgramExecutionTime).seconds))
