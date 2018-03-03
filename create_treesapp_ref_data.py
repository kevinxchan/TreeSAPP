#!/usr/bin/env python3

__author__ = "Connor Morgan-Lang"
__maintainer__ = "Connor Morgan-Lang"
__license__ = "GPL"
__version__ = "0.0.2"

try:
    import argparse
    import sys
    import os
    import shutil
    import re
    import traceback

    from time import gmtime, strftime

    from utilities import os_type, is_exe, which, find_executables, reformat_string, get_lineage, generate_blast_database
    from fasta import format_read_fasta, get_headers, get_header_format
    from classy import ReferenceSequence
    from external_command_interface import launch_write_command

except ImportError:
    sys.stderr.write("Could not load some user defined module functions:\n")
    sys.stderr.write(str(traceback.print_exc(10)))
    sys.exit(3)


def get_arguments():
    parser = argparse.ArgumentParser(add_help=False, formatter_class=argparse.RawTextHelpFormatter)
    required_args = parser.add_argument_group("Required arguments")
    required_args.add_argument("-i", "--fasta_input",
                               help="FASTA file that will be used to create reference data for TreeSAPP",
                               required=True)
    required_args.add_argument("-c", "--code_name",
                               help="Unique name to be used by TreeSAPP internally. NOTE: Must be <=6 characters.\n"
                                    "(Refer to first column of 'cog_list.txt' under the '#functional cogs' section)",
                               required=True)
    required_args.add_argument("-p", "--identity",
                               help="The percent identity which the input sequences were clustered",
                               required=True,
                               type=str)

    optopt = parser.add_argument_group("Optional options")
    optopt.add_argument("-u", "--uc",
                        help="The USEARCH cluster format file produced from clustering reference sequences",
                        required=False,
                        default=None)
    optopt.add_argument('-l', '--min_seq_length',
                        help='Minimal sequence length [DEFAULT = 50]',
                        required=False,
                        default=50,
                        type=int)
    optopt.add_argument('-a', '--multiple_alignment',
                        help='The FASTA input is also the multiple alignment file to be used.\n'
                             'In this workflow, alignment with MUSCLE is skipped and this file is used instead.',
                        action="store_true",
                        default=False)
    optopt.add_argument('-m', '--molecule',
                        help='The type of input sequences:\n'
                             'prot = Protein [DEFAULT]; dna = Nucleotide; rrna = rRNA',
                        default='prot',
                        choices=['prot', 'dna', 'rrna'])
    optopt.add_argument('-r', "--rfam_cm",
                        help="The covariance model of the RNA family being packaged.\n"
                             "REQUIRED if molecule is rRNA!",
                        default=None)
    optopt.add_argument("-b", "--bootstraps",
                        help="The number of bootstrap replicates RAxML should perform\n"
                             "[ DEFAULT = autoMR ]",
                        required=False,
                        default="autoMR")
    optopt.add_argument("-e", "--raxml_model",
                        help="The evolutionary model for RAxML to use\n"
                             "[ Proteins = PROTGAMMAAUTO | Nucleotides =  GTRGAMMA ]",
                        required=False,
                        default=None)
    optopt.add_argument("-T", "--num_threads",
                        help="The number of threads for RAxML to use [ DEFAULT = 4 ]",
                        required=False,
                        default=str(4),
                        type=str)
    optopt.add_argument("-s", "--screen",
                        help="Keywords (taxonomic regular expressions) for including specific taxa in the tree.\n"
                             "Example: to only include Bacteria and Archaea do `--screen Bacteria,Archaea`\n"
                             "[ DEFAULT is no screen ]",
                        default="",
                        required=False)
    optopt.add_argument("-f", "--filter",
                        help="Keywords for removing specific taxa; the opposite of `--screen`.\n"
                             "[ DEFAULT is no filter ]",
                        default="",
                        required=False)
    optopt.add_argument("-o", "--output_dir",
                        help="Path to a directory for all outputs [ DEFAULT = ./ ]",
                        default="./",
                        required=False)
    miscellaneous_opts = parser.add_argument_group("Miscellaneous options")
    miscellaneous_opts.add_argument('--overwrite', action='store_true', default=False,
                                    help='Overwrites previously processed output folders')
    miscellaneous_opts.add_argument('--pc', action='store_true', default=False,
                                    help='Prints the final commands to complete\n'
                                         'installation for a provided `code_name`')
    miscellaneous_opts.add_argument('--add_lineage', action='store_true', default=False,
                                    help='If the tax_ids file exists for the code_name,\n'
                                         'the third (lineage) column is appended then exits,\n'
                                         'leaving all other files.')
    miscellaneous_opts.add_argument('-v', '--verbose', action='store_true', default=False,
                                    help='Prints a more verbose runtime log')
    miscellaneous_opts.add_argument("-h", "--help",
                                    action="help",
                                    help="Show this help message and exit")

    args = parser.parse_args()
    args.treesapp = os.path.abspath(os.path.dirname(os.path.realpath(__file__))) + os.sep
    if args.output_dir[0] != os.sep:
        # The user didn't provide a full path
        args.output_dir = os.getcwd() + os.sep + args.output_dir
    if args.output_dir[-1] != os.sep:
        args.output_dir += os.sep
    args.output = args.output_dir + "TreeSAPP_files_%s" % args.code_name + os.sep

    if len(args.code_name) > 6:
        sys.stderr.write("ERROR: code_name must be <= 6 characters!\n")
        sys.stderr.flush()
        sys.exit(-1)

    if args.rfam_cm is None and args.molecule == "rrna":
        sys.stderr.write("ERROR: Covariance model file must be provided for rRNA data!\n")
        sys.exit(-2)

    # Check the RAxML model
    raxml_models = ["PROTGAMMAWAG", "PROTGAMMAAUTO", "PROTGAMMALGF", "GTRCAT", "GTRCATI ", "GTRCATX", "GTRGAMMA",
                    "ASC_GTRGAMMA", "ASC_GTRCAT", "BINGAMMA", "PROTGAMMAILGX", "PROTGTRGAMMA"]
    if args.raxml_model and args.raxml_model not in raxml_models:
        sys.stderr.write("ERROR: --raxml_model (" + args.raxml_model + ") not valid!\n")
        sys.stderr.write("If this model is valid (not a typo), add if to `raxml_models` list and re-run.\n")
        sys.exit(3)

    return args


def read_phylip(phylip_input):
    header_dict = dict()
    alignment_dict = dict()
    x = 0

    try:
        phylip = open(phylip_input, 'r')
    except IOError:
        raise IOError("ERROR: Unable to open the Phylip file (" + phylip_input + ") provided for reading!")

    line = phylip.readline()
    try:
        num_sequences, aln_length = line.strip().split(' ')
        num_sequences = int(num_sequences)
        aln_length = int(aln_length)
    except ValueError:
        raise AssertionError("ERROR: Phylip file is not formatted correctly!\n"
                             "Header line does not contain 2 space-separated fields "
                             "(number of sequences and alignment length). Exiting now.\n")
    line = phylip.readline()
    while line:
        line = line.strip()
        if len(line.split()) == 2:
            # This is the introduction set: header, sequence
            header, sequence = line.split()
            header_dict[x] = header
            alignment_dict[x] = sequence
            x += 1
        elif 60 >= len(line) >= 1:
            alignment_dict[x] += line
            x += 1
        elif line == "":
            # Reset accumulator on blank lines
            x = 0
        else:
            sys.exit(line + "\nERROR: Unexpected line in Phylip file.")

        line = phylip.readline()

        if x > num_sequences:
            sys.stderr.write("\nERROR:\n"
                             "Accumulator has exceeded the number of sequences in the file (according to header)!\n")
            sys.exit()

    # Check that the alignment length matches that in the header line
    x = 0
    while x < num_sequences-1:
        if len(alignment_dict[x]) != aln_length:
            sys.stderr.write("\nERROR:\n" + header_dict[x] +
                             " sequence length exceeds the stated multiple alignment length (according to header)!\n")
            sys.stderr.write("sequence length = " + str(len(alignment_dict[x])) +
                             ", alignment length = " + str(aln_length) + "\n")
            sys.exit()
        else:
            pass
        x += 1

    phylip.close()
    return header_dict, alignment_dict


def write_mfa(header_dict, alignment_dict, fasta_output):
    fasta_string = ""

    for entry in header_dict:
        fasta_string += '>' + header_dict[entry] + "\n"
        fasta_string += alignment_dict[entry] + "\n"

    try:
        fasta = open(fasta_output, 'w')
    except IOError:
        raise IOError("ERROR: Unable to open the FASTA file (" + fasta_output + ") provided for writing!")
    fasta.write(fasta_string)
    fasta.close()

    return


def phylip_to_mfa(phylip_input, fasta_output):
    header_dict, alignment_dict = read_phylip(phylip_input)
    write_mfa(header_dict, alignment_dict, fasta_output)


def generate_cm_data(args, unaligned_fasta):
    """
    Using the input unaligned FASTA file:
     1. align the sequences using cmalign against a reference Rfam covariance model to generate a Stockholm file
     2. use the Stockholm file (with secondary structure annotated) to build a covariance model
     3. align the sequences using cmalign against a reference Rfam covariance model to generate an aligned fasta (AFA)
    :param args: command-line arguments objects
    :param unaligned_fasta:
    :return:
    """
    sys.stdout.write("Running cmalign to build Stockholm file with secondary structure annotations... ")
    sys.stdout.flush()

    cmalign_base = [args.executables["cmalign"],
                    "--mxsize", str(3084),
                    "--informat", "FASTA",
                    "--cpu", str(args.num_threads)]
    # First, generate the stockholm file
    cmalign_sto = cmalign_base + ["-o", args.code_name + ".sto"]
    cmalign_sto += [args.rfam_cm, unaligned_fasta]

    stdout, cmalign_pro_returncode = launch_write_command(cmalign_sto)

    if cmalign_pro_returncode != 0:
        sys.stderr.write("ERROR: cmalign did not complete successfully for:\n")
        sys.stderr.write(' '.join(cmalign_sto) + "\n")
        sys.exit()

    sys.stdout.write("done.\n")
    sys.stdout.write("Running cmbuild... ")
    sys.stdout.flush()

    # Build the CM
    cmbuild_command = [args.executables["cmbuild"]]
    cmbuild_command += ["-n", args.code_name]
    cmbuild_command += [args.code_name + ".cm", args.code_name + ".sto"]

    stdout, cmbuild_pro_returncode = launch_write_command(cmbuild_command)

    if cmbuild_pro_returncode != 0:
        sys.stderr.write("ERROR: cmbuild did not complete successfully for:\n")
        sys.stderr.write(' '.join(cmbuild_command) + "\n")
        sys.exit()
    os.rename(args.code_name + ".cm", args.output + os.sep + args.code_name + ".cm")
    if os.path.isfile(args.output + os.sep + args.code_name + ".sto"):
        sys.stderr.write("WARNING: overwriting " + args.output + os.sep + args.code_name + ".sto")
        sys.stderr.flush()
        os.remove(args.output + os.sep + args.code_name + ".sto")
    shutil.move(args.code_name + ".sto", args.output)

    sys.stdout.write("done.\n")
    sys.stdout.write("Running cmalign to build MSA... ")
    sys.stdout.flush()

    # Generate the aligned FASTA file which will be used to build the BLAST database and tree with RAxML
    aligned_fasta = args.code_name + ".fc.repl.aligned.fasta"
    cmalign_afa = cmalign_base + ["--outformat", "Phylip"]
    cmalign_afa += ["-o", args.code_name + ".phy"]
    cmalign_afa += [args.rfam_cm, unaligned_fasta]

    stdout, cmalign_pro_returncode = launch_write_command(cmalign_afa)

    if cmalign_pro_returncode != 0:
        sys.stderr.write("ERROR: cmalign did not complete successfully for:\n")
        sys.stderr.write(' '.join(cmalign_afa) + "\n")
        sys.exit()

    # Convert the Phylip file to an aligned FASTA file for downstream use
    phylip_to_mfa(args.code_name + ".phy", aligned_fasta)

    sys.stdout.write("done.\n")
    sys.stdout.flush()

    return aligned_fasta


def create_new_fasta(out_fasta, ref_seq_dict, dashes=False):
    """
    Writes a new FASTA file using a dictionary of ReferenceSequence class objects
    :param out_fasta: Name of the FASTA file to write to
    :param ref_seq_dict: Dictionary containing ReferenceSequence objects, numbers are keys
    :param dashes: Flag indicating whether hyphens should be retained from sequences
    :return:
    """
    out_fasta_handle = open(out_fasta, "w")
    num_seqs_written = 0

    for mltree_id in sorted(ref_seq_dict, key=int):
        ref_seq = ref_seq_dict[mltree_id]
        if dashes is False:
            sequence = re.sub('[-.]', '', ref_seq.sequence)
        else:
            # sequence = re.sub('\.', '', ref_seq.sequence)
            sequence = ref_seq.sequence
        out_fasta_handle.write(">" + ref_seq.short_id + "\n" + sequence + "\n")
        num_seqs_written += 1

    out_fasta_handle.close()

    if num_seqs_written == 0:
        sys.stderr.write("ERROR: No sequences written to " + out_fasta + ".\n")
        sys.stderr.write("The headers in your input file are probably not accommodated in the regex patterns used. "
                         "Function responsible: get_header_format. Please make an issue on the GitHub page.\n")
        sys.stderr.flush()
        sys.exit(5)

    return


def read_uc(uc_file):
    """
    Function to read a USEARCH cluster (.uc) file
    :param uc_file: Path to a .uc file produced by USEARCH
    :return: Dictionary where keys are representative cluster headers and the values are headers of identical sequences
    """
    cluster_dict = dict()
    try:
        uc = open(uc_file, 'r')
    except IOError:
        raise IOError("Unable to open USEARCH cluster file " + uc_file + " for reading! Exiting...")

    line = uc.readline()
    # Find all clusters with multiple identical sequences
    while line:
        # TODO: Figure out why some are not added to cluster_dict
        cluster_type, _, length, identity, _, _, _, cigar, header, representative = line.strip().split("\t")
        if cluster_type != "C":
            try:
                identity = float(identity)
            except ValueError:
                identity = "*"
            if cluster_type == "S":
                cluster_dict['>' + header] = list()
            if cluster_type == "H" and identity == 100.0 and cigar == '=':
                cluster_dict['>' + representative].append('>' + header)
        line = uc.readline()
    return cluster_dict


def regenerate_cluster_rep_swaps(args, cluster_dict, fasta_replace_dict):
    """
    Function to regenerate the swappers dictionary with the original headers as keys and
    the new header (swapped in the previous attempt based on USEARCH's uc file) as a value
    :param args: command-line arguments objects
    :param cluster_dict: Dictionary where keys are centroid headers and values are headers of identical sequences
    :param fasta_replace_dict: Immature (lacking sequences) dictionary with header information parsed from tax_ids file
    :return:
    """
    swappers = dict()
    if args.verbose:
        sys.stderr.write("Centroids with identical sequences in the unclustered input file:\n")
    for rep in sorted(cluster_dict):
        matched = False
        subs = cluster_dict[rep]
        # If its entry in cluster_dict == 0 then there were no identical
        # sequences and the header could not have been swapped
        if len(subs) >= 1:
            # If there is the possibility the header could have been swapped,
            # check if the header is in fasta_replace_dict
            for mltree_id in fasta_replace_dict:
                if matched:
                    break
                ref_seq = fasta_replace_dict[mltree_id]
                # If the accession from the tax_ids file is the same as the representative
                # this one has not been swapped for an identical sequence's header since it is in use
                if re.search(ref_seq.accession, rep):
                    if args.verbose:
                        sys.stderr.write("\tUnchanged: " + rep + "\n")
                        matched = True
                    break
                # The original representative is no longer in the reference sequences
                # so it was replaced, with this sequence...
                for candidate in subs:
                    if rep in swappers or matched:
                        break

                    # parse the accession from the header
                    header_format_re, header_db, header_molecule = get_header_format(candidate, args.code_name)
                    sequence_info = header_format_re.match(candidate)
                    if sequence_info:
                        candidate_acc = sequence_info.group(1)
                    else:
                        sys.stdout.write("Unable to handle header: " + candidate + "\n")
                        sys.exit()

                    # Now compare...
                    if candidate_acc == ref_seq.accession:
                        if args.verbose:
                            sys.stderr.write("\tChanged: " + candidate + "\n")
                        swappers[rep] = candidate
                        matched = True
                        break
            sys.stderr.flush()
    return swappers


def present_cluster_rep_options(cluster_dict):
    """
    Present the headers of identical sequences to user for them to decide on representative header
    :param cluster_dict: dictionary from read_uc(uc_file)
    :return:
    """
    swappers = dict()
    candidates = dict()

    for rep in cluster_dict:
        candidates.clear()
        subs = cluster_dict[rep]
        if len(subs) >= 1:
            sys.stderr.write("Found multiple identical sequences in cluster file:\n")
            candidates[str(1)] = rep
            acc = 2
            for candidate in subs:
                candidates[str(acc)] = candidate
                acc += 1
            for num in sorted(candidates.keys(), key=int):
                sys.stderr.write(num + ". " + candidates[num] + "\n")
            sys.stderr.flush()
            best = input("Number of the best representative? ")
            # Useful for testing - no need to pick which sequence name is best!
            # best = str(1)
            while best not in candidates.keys():
                best = input("Invalid number. Number of the best representative? ")
            if best != str(1):
                swappers[rep] = candidates[best]

    return swappers


def reformat_headers(header_dict):
    """
    Imitate format_read_fasta header name reformatting
    :param header_dict: Dictionary of old header : new header key : value pairs
    :return:
    """
    swappers = dict()

    for old, new in header_dict.items():
        swappers[reformat_string(old)] = reformat_string(new)
    return swappers


def map_good_headers_to_ugly(header_collection):
    """
    Pairs a "good" header (bad characters replaced) with an original header which is needed for parsing information
    from the header (such as organism ID, description, locus) in the next stage
    :param header_collection: A dictionary or list containing original, unmodified headers
    :return:
    """
    header_map = dict()
    if type(header_collection) is list:
        # These are the headers from the input FASTA file
        header_list = header_collection
    elif type(header_collection) is dict:
        # These are the headers from USEARCH's uc file
        header_list = list(header_collection.keys())
        for key in header_collection.keys():
            header_list += header_collection[key]
    else:
        sys.stderr.write("ERROR: Unknown header_collection format! Expected list or dict.\n")
        raise AssertionError

    for original_header in sorted(header_list):
        header_map[reformat_string(original_header)] = original_header
    return header_map


def return_sequence_info_groups(regex_match_groups, header_db, header):
    accession = ""
    description = ""
    locus = ""
    organism = ""
    if regex_match_groups:
        if len(regex_match_groups.groups()) == 2:
            accession = regex_match_groups.group(1)
            organism = regex_match_groups.group(2)
            description = regex_match_groups.group(2)
        elif header_db in ["ncbi_ambig", "refseq_prot", "gen_genome"]:
            accession = regex_match_groups.group(1)
            description = regex_match_groups.group(2)
            organism = regex_match_groups.group(3)
        elif header_db == "silva":
            accession = regex_match_groups.group(1)
            locus = str(regex_match_groups.group(2)) + '-' + str(regex_match_groups.group(3))
            organism = regex_match_groups.group(4)
            description = regex_match_groups.group(4)
        elif header_db == "fungene":
            accession = regex_match_groups.group(1)
            locus = regex_match_groups.group(2)
            organism = regex_match_groups.group(3)
            description = regex_match_groups.group(3)
        elif header_db == "fungene_truncated":
            accession = regex_match_groups.group(1)
            organism = regex_match_groups.group(2)
            description = regex_match_groups.group(3)
    else:
        sys.stderr.write("Unable to handle header: " + header + "\n")
        sys.exit()

    if not accession and not organism:
        sys.stderr.write("ERROR: Insufficient information was loaded for header:\n" + header + "\n")
        sys.stderr.write("regex_match: " + header_db + '\n')
        sys.exit(33)

    return accession, organism, locus, description


def get_sequence_info(code_name, fasta_dict, fasta_replace_dict, header_map, swappers=None):
    """
    This function is used to find the accession ID and description of each sequence from the FASTA file
    :param code_name: code_name from the command-line parameters
    :param fasta_dict: a dictionary with headers as keys and sequences as values (returned by format_read_fasta)
    :param fasta_replace_dict:
    :param header_map:
    :param swappers: A dictionary containing representative clusters (keys) and their constituents (values)
    :return: fasta_replace_dict with a complete ReferenceSequence() value for every mltree_id key
    """

    sys.stdout.write("Extracting information from headers for formatting purposes... ")
    sys.stdout.flush()
    fungene_gi_bad = re.compile("^>[0-9]+\s+coded_by=.+,organism=.+,definition=.+$")
    mltree_id_accumulator = 1
    swapped_headers = []
    if len(fasta_replace_dict.keys()) > 0:
        for mltree_id in sorted(fasta_replace_dict):
            ref_seq = fasta_replace_dict[mltree_id]
            ref_seq.short_id = mltree_id + '_' + code_name
            for header in fasta_dict:
                original_header = header_map[header]
                header_format_re, header_db, header_molecule = get_header_format(original_header, code_name)
                sequence_info = header_format_re.match(original_header)
                _, fasta_header_organism, _, _ = return_sequence_info_groups(sequence_info, header_db, header)
                if re.search(ref_seq.accession, header):
                    if re.search(reformat_string(ref_seq.organism), reformat_string(fasta_header_organism)):
                        ref_seq.sequence = fasta_dict[header]
                    else:
                        sys.stderr.write("\nWARNING: " +
                                         "accession (" + ref_seq.accession + ") matches, organism differs:\n")
                        sys.stderr.write('"' + ref_seq.organism + "\" versus \"" + fasta_header_organism + "\"\n")
            if not ref_seq.sequence:
                # Ensure the header isn't a value within the swappers dictionary
                for swapped in swappers.keys():
                    header = swappers[swapped]
                    original_header = header_map[header]
                    if re.search(ref_seq.accession, header) and re.search(ref_seq.organism, original_header):
                        # It is and therefore the header was swapped last run
                        ref_seq.sequence = fasta_dict[swapped]
                        break
                if not ref_seq.sequence:
                    # Unable to find sequence in swappers too
                    sys.exit("Unable to find header for " + ref_seq.accession)

    else:  # if fasta_replace_dict needs to be populated, this is a new run
        for header in sorted(fasta_dict.keys()):
            if fungene_gi_bad.match(header):
                sys.stderr.write("\nWARNING: Input sequences use 'GIs' which are obsolete and may be non-unique. "
                                 "For everyone's sanity, please download sequences with the `accno` instead.\n")
                sys.exit()
            mltree_id = str(mltree_id_accumulator)
            ref_seq = ReferenceSequence()
            ref_seq.sequence = fasta_dict[header]
            if swappers and header in swappers.keys():
                header = swappers[header]
                swapped_headers.append(header)
            if header in header_map:
                original_header = header_map[header]
            else:
                sys.stderr.write("ERROR: unable to find " + header +
                                 " in header_map (constructed from either the input FASTA or .uc file).\n")
                sys.stderr.write("There is a chance this is due to the FASTA file and .uc being generated separately.\n")
                # sys.stderr.write("This is probably an error stemming from `reformat_string()`.\n")
                sys.exit()
            header_format_re, header_db, header_molecule = get_header_format(original_header, code_name)
            sequence_info = header_format_re.match(original_header)
            ref_seq.accession,\
            ref_seq.organism,\
            ref_seq.locus,\
            ref_seq.description = return_sequence_info_groups(sequence_info, header_db, original_header)

            ref_seq.short_id = mltree_id + '_' + code_name
            fasta_replace_dict[mltree_id] = ref_seq

            mltree_id_accumulator += 1
        if swappers and len(swapped_headers) != len(swappers):
            sys.stderr.write("\nERROR: Some headers that were meant to be replaced could not be compared!\n")
            for header in swappers.keys():
                if header not in swapped_headers:
                    sys.stdout.write(header + "\n")
            sys.exit()

    sys.stdout.write("done.\n")
    sys.stdout.flush()

    return fasta_replace_dict


def screen_filter_taxa(args, fasta_replace_dict):
    if args.screen == "" and args.filter == "":
        return fasta_replace_dict
    else:
        if args.screen:
            screen_terms = args.screen.split(',')
        else:
            screen_terms = ''
        if args.filter:
            filter_terms = args.filter.split(',')
        else:
            filter_terms = ''

    purified_fasta_dict = dict()
    num_filtered = 0
    num_screened = 0

    for mltree_id in fasta_replace_dict:
        screen_pass = False
        filter_pass = True
        ref_seq = fasta_replace_dict[mltree_id]
        # Screen
        if len(screen_terms) > 0:
            for term in screen_terms:
                # If any term is found in the lineage, it will pass... unless it fails the filter
                if re.search(term, ref_seq.lineage):
                    screen_pass = True
                    break
        else:
            screen_pass = True
        # Filter
        if len(filter_terms) > 0:
            for term in filter_terms:
                if re.search(term, ref_seq.lineage):
                    filter_pass = False

        if filter_pass and screen_pass:
            purified_fasta_dict[mltree_id] = ref_seq
        else:
            if screen_pass is False:
                num_screened += 1
            if filter_pass is False:
                num_filtered += 1

    if args.verbose:
        sys.stdout.write('\t' + str(num_screened) + " sequences removed after failing screen.\n")
        sys.stdout.write('\t' + str(num_filtered) + " sequences removed after failing filter.\n")
        sys.stdout.write('\t' + str(len(purified_fasta_dict.keys())) + " sequences retained for building tree.\n")
        sys.stdout.flush()

    return purified_fasta_dict


def order_dict_by_lineage(fasta_replace_dict):
    # Create a new dictionary with lineages as keys
    lineage_dict = dict()
    sorted_lineage_dict = dict()
    for mltree_id in fasta_replace_dict:
        ref_seq = fasta_replace_dict[mltree_id]
        if ref_seq.lineage not in lineage_dict.keys():
            # Values of the new dictionary are lists of ReferenceSequence instances
            lineage_dict[ref_seq.lineage] = list()
        lineage_dict[ref_seq.lineage].append(ref_seq)
    mltree_key = 1
    for lineage in sorted(lineage_dict.keys(), key=str):
        for ref_seq in lineage_dict[lineage]:
            # Replace the mltree_id object
            code = '_'.join(ref_seq.short_id.split('_')[1:])
            ref_seq.short_id = str(mltree_key) + '_' + code
            sorted_lineage_dict[str(mltree_key)] = ref_seq
            mltree_key += 1

    return sorted_lineage_dict


def threshold(lst, confidence="low"):
    """

    :param lst:
    :param confidence:
    :return:
    """
    if confidence == "low":
        # Majority calculation
        index = round(len(lst)*0.51)-1
    elif confidence == "medium":
        # >=75% of the list is reported
        index = round(len(lst)*0.75)-1
    else:
        # confidence is "high" and >=90% of the list is reported
        index = round(len(lst)*0.9)-1
    return sorted(lst, reverse=True)[index]


def estimate_taxonomic_redundancy(args, reference_dict):
    """

    :param args:
    :param reference_dict:
    :return:
    """
    # TODO: Factor proximity of leaves in the tree into this measure
    # For instance, if the two or so species of the same genus are in the tree,
    # are they also beside each other in the same clade or are they located in different clusters?
    lowest_reliable_rank = "Strain"
    rank_depth_map = {1: "Kingdoms", 2: "Phyla", 3: "Classes", 4: "Orders", 5: "Families", 6: "Genera", 7: "Species"}
    taxa_counts = dict()
    for depth in rank_depth_map:
        name = rank_depth_map[depth]
        taxa_counts[name] = dict()
    for mltree_id_key in sorted(reference_dict.keys(), key=int):
        lineage = reference_dict[mltree_id_key].lineage
        position = 1
        taxa = lineage.split('; ')
        while position < len(taxa) and position < 8:
            if taxa[position] not in taxa_counts[rank_depth_map[position]]:
                taxa_counts[rank_depth_map[position]][taxa[position]] = 0
            taxa_counts[rank_depth_map[position]][taxa[position]] += 1
            position += 1
    for depth in rank_depth_map:
        rank = rank_depth_map[depth]
        redundancy = list()
        for taxon in taxa_counts[rank]:
            redundancy.append(taxa_counts[rank][taxon])
        if threshold(redundancy, "medium") == 1:
            lowest_reliable_rank = rank
            break

    sys.stdout.write("Lowest reliable rank for taxonomic classification is: " + lowest_reliable_rank + "\n")

    return lowest_reliable_rank


def summarize_reference_taxa(reference_dict):
    # Not really interested in Cellular Organisms or Strains.
    rank_depth_map = {1: "Kingdoms", 2: "Phyla", 3: "Classes", 4: "Orders", 5: "Families", 6: "Genera", 7: "Species"}
    taxa_counts = dict()
    for depth in rank_depth_map:
        name = rank_depth_map[depth]
        taxa_counts[name] = set()
    for mltree_id_key in sorted(reference_dict.keys(), key=int):
        lineage = reference_dict[mltree_id_key].lineage
        position = 1
        taxa = lineage.split('; ')
        while position < len(taxa) and position < 8:
            taxa_counts[rank_depth_map[position]].add(taxa[position])
            position += 1
    sys.stdout.write("Number of unique lineages:\n")
    for depth in rank_depth_map:
        rank = rank_depth_map[depth]
        buffer = " "
        while len(rank) + len(str(len(taxa_counts[rank]))) + len(buffer) < 12:
            buffer += ' '
        sys.stdout.write("\t" + rank + buffer + str(len(taxa_counts[rank])) + "\n")
    sys.stdout.flush()

    return


def check_lineage(lineage, organism_name):
    """
    Sometimes the NCBI lineage is incomplete.
    Currently, this function uses organism_name to ideally add Species to the lineage
    :param lineage: A semi-colon separated taxonomic lineage
    :param organism_name: Name of the organism. Parsed from the sequence header (usually at the end in square brackets)
    :return: A string with lineage information
    """
    proper_species_re = re.compile("^[A-Z][a-z]+ [a-z]+$")
    if proper_species_re.match(lineage.split("; ")[-1]):
        return lineage
    elif len(lineage.split("; ")) == 7 and proper_species_re.match(organism_name):
        return lineage + "; " + organism_name
    else:
        return lineage


def write_tax_ids(args, fasta_replace_dict, tree_taxa_list, molecule):
    """
    Write the number, organism and accession ID, if possible
    :param args: command-line arguments objects, used for screen and filter regex
    :param fasta_replace_dict:
    :param tree_taxa_list: The name of the output file
    :param molecule: "dna", "rrna", or "prot" - parsed from command line arguments
    :return:
    """
    sys.stdout.write("Retrieving lineage information for each reference sequence... ")
    sys.stdout.flush()

    # Prepare for the progress bar
    num_reference_sequences = len(fasta_replace_dict.keys())
    if num_reference_sequences > 50:
        progress_bar_width = 50
        step_proportion = float(num_reference_sequences) / progress_bar_width
    else:
        progress_bar_width = num_reference_sequences
        step_proportion = 1

    sys.stdout.write("[%s ]" % (" " * progress_bar_width))
    sys.stdout.write("%")
    sys.stdout.write("\b" * (progress_bar_width + 3))
    sys.stdout.flush()

    acc = 0.0

    taxa_searched = 0
    tree_taxa_string = ""
    for mltree_id_key in fasta_replace_dict.keys():
        reference_sequence = fasta_replace_dict[mltree_id_key]
        acc += 1.0
        if acc >= step_proportion:
            acc -= step_proportion
            sys.stdout.write("-")
            sys.stdout.flush()

        taxa_searched += 1
        if reference_sequence.lineage:
            continue

        lineage = ""
        strikes = 0
        while strikes < 3:
            if strikes == 0:
                if not reference_sequence.accession:
                    sys.stderr.write("WARNING: no accession available for Entrez query:\n")
                    reference_sequence.get_info()
                lineage = get_lineage(reference_sequence.accession, molecule)
                if type(lineage) is str:
                    # The query was successful
                    strikes = 3
            elif strikes == 1:
                # Unable to determine lineage from the search_term provided,
                # try to parse organism name from description
                if reference_sequence.organism:
                    try:
                        taxon = reference_sequence.organism.split('_')[-2]
                    except IndexError:
                        taxon = reference_sequence.organism
                    lineage = get_lineage(taxon, "tax")
                    if type(lineage) is str:
                        # The query was successful
                        lineage += '; ' + reference_sequence.organism.split('_')[-2]
                        strikes = 3
                else:
                    # Organism information is not available, time to bail
                    strikes += 1
            elif strikes == 2:
                lineage = get_lineage(lineage, "tax")
            strikes += 1
        if not lineage:
            sys.stderr.write("\nWARNING: Unable to find lineage for sequence with following data:\n")
            fasta_replace_dict[mltree_id_key].get_info()
            lineage = "Unclassified"
        # TODO: test this
        if reference_sequence.organism:
            lineage = check_lineage(lineage, reference_sequence.organism)
        else:
            reference_sequence.organism = reference_sequence.description
        reference_sequence.lineage = lineage

    sys.stdout.write("] done.\n")
    sys.stdout.flush()

    if taxa_searched != len(fasta_replace_dict.keys()):
        sys.stderr.write("ERROR: Not all sequences (" + str(taxa_searched) + '/'
                         + str(len(fasta_replace_dict.keys())) + ") were queried against the NCBI taxonomy database!\n")
        sys.exit(22)

    if args.add_lineage:
        if args.screen or args.filter:
            sys.stderr.write("WARNING: Skipping taxonomic filtering and screening in `--add_lineage` mode.\n")
    else:
        fasta_replace_dict = order_dict_by_lineage(fasta_replace_dict)
        fasta_replace_dict = screen_filter_taxa(args, fasta_replace_dict)

    for mltree_id_key in sorted(fasta_replace_dict.keys(), key=int):
        # Definitely will not uphold phylogenetic relationships but at least sequences
        # will be in the right neighbourhood rather than ordered by their position in the FASTA file
        reference_sequence = fasta_replace_dict[mltree_id_key]
        tree_taxa_string += "%s\t%s | %s\t%s\n" % (str(mltree_id_key),
                                                   reference_sequence.organism,
                                                   reference_sequence.accession,
                                                   reference_sequence.lineage)
    tree_tax_list_handle = open(tree_taxa_list, "w")
    tree_tax_list_handle.write(tree_taxa_string)
    tree_tax_list_handle.close()

    return fasta_replace_dict


def read_tax_ids(tree_taxa_list):
    """
    Reads the taxonomy and accession ID affiliated with each sequence number.
    This information is used to avoid horrible manual work if the pipeline is ran multiple times
    :param tree_taxa_list: The name of the tax_ids file to read
    :return:
    """
    try:
        tree_tax_list_handle = open(tree_taxa_list, 'r')
    except IOError:
        raise IOError("Unable to open taxa list " + tree_taxa_list + " for reading! Exiting.")
    fasta_replace_dict = dict()
    line = tree_tax_list_handle.readline()
    while line:
        fields = line.strip().split("\t")
        if len(fields) == 3:
            mltree_id_key, seq_info, lineage = fields
        else:
            mltree_id_key, seq_info = fields
            lineage = ""
        ref_seq = ReferenceSequence()
        ref_seq.organism = seq_info.split(" | ")[0]
        ref_seq.accession = seq_info.split(" | ")[1]
        ref_seq.lineage = lineage
        fasta_replace_dict[mltree_id_key] = ref_seq
        line = tree_tax_list_handle.readline()
    tree_tax_list_handle.close()

    return fasta_replace_dict


def swap_tree_names(tree_to_swap, final_mltree, code_name):
    original_tree = open(tree_to_swap, 'r')
    raxml_tree = open(final_mltree, 'w')

    tree = original_tree.readlines()
    original_tree.close()
    if len(tree) > 1:
        sys.stderr.write("ERROR: >1 line contained in RAxML tree " + tree_to_swap)

    new_tree = re.sub('_' + re.escape(code_name), '', str(tree[0]))
    raxml_tree.write(new_tree)

    raxml_tree.close()
    return


def annotate_partition_tree(code_name, fasta_replace_dict, bipart_tree):
    try:
        tree_txt = open(bipart_tree, 'r')
    except IOError:
        raise IOError("Unable to open RAxML bipartition tree " + bipart_tree + " for reading.")

    tree = tree_txt.readline()
    tree_txt.close()
    for mltree_id_key in fasta_replace_dict.keys():
        tree = re.sub('\(' + mltree_id_key + "_" + code_name, '(' + fasta_replace_dict[mltree_id_key].organism, tree)
        tree = re.sub(',' + mltree_id_key + "_" + code_name, ',' + fasta_replace_dict[mltree_id_key].organism, tree)

    raxml_out = os.path.dirname(bipart_tree)
    annotated_tree_name = raxml_out + os.sep + "RAxML_bipartitions_annotated." + code_name
    try:
        annotated_tree = open(annotated_tree_name, 'w')
    except IOError:
        raise IOError("Unable to open the annotated RAxML tree " + annotated_tree_name + " for writing!")

    annotated_tree.write(tree)
    annotated_tree.close()

    return


def find_model_used(raxml_info_file):
    model_statement_re = re.compile(r".* model: ([A-Z]+) likelihood.*")
    model = ""
    command_line = ""
    with open(raxml_info_file) as raxml_info:
        for line in raxml_info:
            if model_statement_re.search(line):
                model = model_statement_re.search(line).group(1)
                break
            elif re.match('^.*/raxml.*-m ([A-Z]+)$', line):
                command_line = line
            else:
                pass
    if model == "":
        if command_line == "":
            sys.stderr.write("WARNING: Unable to parse model used from " + raxml_info_file + "!\n")
            sys.stderr.flush()
        else:
            model = re.match('^.*/raxml.*-m ([A-Z]+)$', command_line).group(1)
    return model


def update_build_parameters(args, code_name, aa_model, lowest_reliable_rank):
    """
    Function to update the data/tree_data/ref_build_parameters.tsv file with information on this new reference sequence
    Format of file is "code_name       denominator     aa_model        cluster_identity        last_updated"
    :param args: command-line arguments objects
    :param code_name: 
    :param aa_model:
    :param lowest_reliable_rank:
    :return: 
    """
    param_file = args.treesapp + "data" + os.sep + "tree_data" + os.sep + "ref_build_parameters.tsv"
    try:
        params = open(param_file, 'a')
    except IOError:
        raise IOError("Unable to open " + param_file + "for appending!")

    date = strftime("%d_%b_%Y", gmtime())

    build_list = [code_name, "Z1111", "PROTGAMMA" + aa_model, args.identity, lowest_reliable_rank, date]
    params.write("\t".join(build_list) + "\n")

    return


def terminal_commands(final_output_folder, code_name):
    sys.stdout.write("\nTo integrate these data for use in TreeSAPP, the following steps must be performed:\n")
    sys.stdout.write("1. Include properly formatted 'denominator' codes "
                     "in data/tree_data/cog_list.tsv and data/tree_data/ref_build_parameters.tsv\n")
    sys.stdout.write("2. $ cp " + final_output_folder + os.sep + "tax_ids_%s.txt" % code_name + " data/tree_data/\n")
    sys.stdout.write("3. $ cp " + final_output_folder + os.sep + code_name + "_tree.txt data/tree_data/\n")
    sys.stdout.write("4. $ cp " + final_output_folder + os.sep + code_name + ".hmm data/hmm_data/\n")
    sys.stdout.write("5. $ cp " + final_output_folder + os.sep + code_name + ".fa* data/alignment_data/\n")
    sys.stdout.write("6. $ cp " + final_output_folder + os.sep + code_name +
                     "_tree.txt imagemaker_2_061/tree_data/\n")
    sys.stdout.write("7. $ cp " + final_output_folder + os.sep + "tax_ids_%s.txt" % code_name +
                     " imagemaker_2_061/tree_data/\n")
    sys.stdout.write("8. Create a file called imagemaker_2_061/tree_data/domain_and_color_descriptions_" +
                     code_name + ".txt to add colours to clades in the new reference tree.\n")
    sys.stdout.write("9. Modify imagemaker_2_061/tree_data/drawing_info.txt following the obvious format\n")
    sys.stdout.flush()
    return


def reverse_complement(rrna_sequence):
    comp = []
    for c in rrna_sequence:
        if c == 'A' or c == 'a':
            comp.append('T')
        if c == 'G' or c == 'g':
            comp.append('C')
        if c == 'U' or c == 'u' or c == 'T' or c == 't':
            comp.append('A')
        if c == 'C' or c == 'c':
            comp.append('G')
        # In the case input FASTA is a multiple alignment file
        if c == '.' or c == '-':
            comp.append(c)
        else:
            pass
    rev_comp = ''.join(reversed(comp))
    return rev_comp


def update_tax_ids_with_lineage(args, tree_taxa_list):
    tax_ids_file = args.treesapp + os.sep + "data" + os.sep + "tree_data" + os.sep + tree_taxa_list
    if not os.path.exists(tax_ids_file):
        sys.stderr.write("ERROR: Unable to find " + tax_ids_file + "!\n")
        raise FileNotFoundError
    else:
        fasta_replace_dict = read_tax_ids(tax_ids_file)
        # Determine how many sequences already have lineage information:
        lineage_info_complete = 0
        for mltree_id_key in fasta_replace_dict:
            ref_seq = fasta_replace_dict[mltree_id_key]
            if ref_seq.lineage:
                lineage_info_complete += 1
        # There are some that are already complete. Should they be over-written?
        if lineage_info_complete >= 1:
            if sys.version_info > (2, 9):
                overwrite_lineages = input(tree_taxa_list + " contains some sequences with complete lineages. "
                                                            "Should they be over-written? [y|n] ")
                while overwrite_lineages != "y" and overwrite_lineages != "n":
                    overwrite_lineages = input("Incorrect response. Please input either 'y' or 'n'. ")
            else:
                overwrite_lineages = raw_input(tree_taxa_list + " contains some sequences with complete lineages."
                                                                "Should they be over-written? [y|n] ")
                while overwrite_lineages != "y" and overwrite_lineages != "n":
                    overwrite_lineages = raw_input("Incorrect response. Please input either 'y' or 'n'. ")
            if overwrite_lineages == 'y':
                ref_seq_dict = dict()
                for mltree_id_key in fasta_replace_dict:
                    ref_seq = fasta_replace_dict[mltree_id_key]
                    if ref_seq.lineage:
                        ref_seq.lineage = ""
                    ref_seq_dict[mltree_id_key] = ref_seq
        write_tax_ids(args, fasta_replace_dict, tax_ids_file, args.molecule)
    return


def main():
    args = get_arguments()
    args = find_executables(args)

    code_name = args.code_name
    final_output_folder = args.output
    if args.pc:
        terminal_commands(final_output_folder, code_name)
        sys.exit(0)

    tree_taxa_list = args.output_dir + "tax_ids_%s.txt" % code_name

    if args.add_lineage:
        update_tax_ids_with_lineage(args, tree_taxa_list)
        terminal_commands(final_output_folder, code_name)
        sys.exit(0)

    if not os.path.exists(final_output_folder):
        try:
            os.makedirs(final_output_folder, exist_ok=False)
        except OSError:
            sys.stderr.write("WARNING: Making all directories in path " + final_output_folder + "\n")
            os.makedirs(final_output_folder, exist_ok=True)

    else:
        sys.stderr.write("WARNING: Output directory already exists. Previous outputs will be overwritten.\n")
        sys.stderr.flush()
        if os.path.exists(args.code_name + "_phy_files"):
            shutil.rmtree(args.code_name + "_phy_files")

    # TODO: Allow for the tax_ids from a previous run to be used even if a uc file isn't provided
    if args.uc and os.path.exists(tree_taxa_list):
        if sys.version_info > (2, 9):
            use_previous_names = input(tree_taxa_list + " found from a previous attempt. "
                                                        "Should it be used for this run? [y|n] ")
            while use_previous_names != "y" and use_previous_names != "n":
                use_previous_names = input("Incorrect response. Please input either 'y' or 'n'. ")
        else:
            use_previous_names = raw_input(tree_taxa_list + " found from a previous attempt. "
                                                            "Should it be used for this run? [y|n] ")
            while use_previous_names != "y" and use_previous_names != "n":
                use_previous_names = raw_input("Incorrect response. Please input either 'y' or 'n'. ")
    else:
        use_previous_names = 'n'

    fasta_dict = format_read_fasta(args.fasta_input, args.molecule, args)

    fasta_replace_dict = dict()

    log = open(args.output_dir + "create_" + code_name + "_treesapp_data_log.txt", 'w')
    log.write("Command used:\n" + ' '.join(sys.argv) + "\n\n")

    if args.uc:
        cluster_dict = read_uc(args.uc)
        header_map = map_good_headers_to_ugly(cluster_dict)
        if use_previous_names == 'n':
            swappers = present_cluster_rep_options(cluster_dict)
        elif use_previous_names == 'y':
            fasta_replace_dict = read_tax_ids(tree_taxa_list)
            if len(fasta_replace_dict.keys()) != len(fasta_dict.keys()):
                raise AssertionError("Number of sequences in new FASTA input and " + tree_taxa_list + " are not equal!")
            swappers = regenerate_cluster_rep_swaps(args, cluster_dict, fasta_replace_dict)
        else:
            sys.exit(2)
        swappers = reformat_headers(swappers)
        fasta_replace_dict = get_sequence_info(code_name, fasta_dict, fasta_replace_dict, header_map, swappers)
        fasta_replace_dict = write_tax_ids(args, fasta_replace_dict, tree_taxa_list, args.molecule)
    else:
        # args.uc is None and use_previous_names == 'n'
        original_headers = get_headers(args.fasta_input)
        header_map = map_good_headers_to_ugly(original_headers)
        fasta_replace_dict = get_sequence_info(code_name, fasta_dict, fasta_replace_dict, header_map)
        fasta_replace_dict = write_tax_ids(args, fasta_replace_dict, tree_taxa_list, args.molecule)

    sys.stdout.write("******************** " + tree_taxa_list + " generated ********************\n")

    if args.verbose:
        summarize_reference_taxa(fasta_replace_dict)
    lowest_reliable_rank = estimate_taxonomic_redundancy(args, fasta_replace_dict)

    fasta_replaced_file = args.output_dir + code_name + ".fc.repl.fasta"
    fasta_mltree = args.output_dir + code_name + ".fa"

    if args.multiple_alignment:
        create_new_fasta(fasta_replaced_file, fasta_replace_dict, True)
    else:
        create_new_fasta(fasta_replaced_file, fasta_replace_dict)

    if args.molecule == 'rrna':
        fasta_replaced_align = generate_cm_data(args, fasta_replaced_file)
        args.multiple_alignment = True
        # fasta_dict = format_read_fasta(aligned_fasta, args.molecule, args)
    elif args.multiple_alignment is False:
        sys.stdout.write("Aligning the sequences using MUSCLE... ")
        fasta_replaced_align = args.output_dir + code_name + ".fc.repl.aligned.fasta"

        muscle_align_command = [args.executables["muscle"]]
        muscle_align_command += ["-in", fasta_replaced_file]
        muscle_align_command += ["-out", fasta_replaced_align]

        stdout, muscle_pro_returncode = launch_write_command(muscle_align_command, False)

        if muscle_pro_returncode != 0:
            sys.stderr.write("ERROR: Multiple sequence alignment using " + args.executables["muscle"] +
                             " did not complete successfully! Command used:\n" + ' '.join(muscle_align_command) + "\n")
            sys.exit()
        sys.stdout.write("done.\n")
    elif args.multiple_alignment and args.molecule != "rrna":
        fasta_replaced_align = fasta_replaced_file
    else:
        pass

    stdout, blastdb = generate_blast_database(args, fasta_replaced_file, args.molecule, args.output_dir + code_name)

    log.write("\n### MAKEBLASTDB ###" + stdout)

    sys.stdout.write("******************** BLAST DB for %s generated ********************\n" % code_name)

    os.rename(fasta_replaced_align, blastdb)

    if args.molecule == "rrna":
        # A .cm file has already been generated, no need for HMM
        pass
    else:
        hmm_build_command = [args.executables["hmmbuild"]]
        hmm_build_command += ["-s", final_output_folder + code_name + ".hmm"]
        hmm_build_command.append(fasta_mltree)

        stdout, hmmbuild_pro_returncode = launch_write_command(hmm_build_command)

        log.write("\n### HMMBUILD ###\n\n" + stdout)
        log.close()

        if hmmbuild_pro_returncode != 0:
            sys.stderr.write("ERROR: hmmbuild did not complete successfully for:\n")
            sys.stderr.write(' '.join(hmm_build_command) + "\n")
            sys.exit()

        sys.stdout.write("******************** HMM file for %s generated ********************\n" % code_name)

    phylip_command = "java -cp %s/sub_binaries/readseq.jar run -a -f=12 %s" % (args.treesapp, fasta_mltree)
    os.system(phylip_command)

    phylip_file = args.output_dir + code_name + ".phy"
    os.rename(fasta_mltree + ".phylip", phylip_file)

    raxml_out = args.output_dir + code_name + "_phy_files"

    if not os.path.exists(raxml_out):
        os.system("mkdir %s" % raxml_out)
    else:
        sys.stderr.write("ERROR: " + raxml_out + " already exists from a previous run! "
                                                 "Please delete or rename it and try again.\n")
        sys.exit()

    raxml_command = [args.executables["raxmlHPC"]]
    raxml_command += ["-f", "a"]
    raxml_command += ["-p", "12345"]
    raxml_command += ["-x", "12345"]
    raxml_command += ["-#", args.bootstraps]
    raxml_command += ["-s", phylip_file]
    raxml_command += ["-n", code_name]
    raxml_command += ["-w", raxml_out]
    raxml_command += ["-T", args.num_threads]

    if args.raxml_model:
        raxml_command += ["-m", args.raxml_model]
    elif args.molecule == "prot":
        raxml_command += ["-m", "PROTGAMMAAUTO"]
    elif args.molecule == "rrna" or args.molecule == "dna":
        raxml_command += ["-m", "GTRGAMMA"]
    else:
        sys.exit("ERROR: a substitution model could not be specified with the 'molecule' argument: " + args.molecule)

    stdout, raxml_returncode = launch_write_command(raxml_command, False)

    if raxml_returncode != 0:
        sys.stderr.write("ERROR: RAxML did not complete successfully! "
                         "Look in " + args.treesapp + raxml_out + os.sep +
                         "RAxML_info." + code_name + " for an error message.\n")
        sys.stderr.write("RAxML command used:\n")
        sys.stderr.write(' '.join(raxml_command) + "\n")
        sys.exit(3)

    tree_to_swap = "%s/RAxML_bestTree.%s" % (raxml_out, code_name)
    final_mltree = "%s_tree.txt" % code_name
    os.system("mv %s %s" % (phylip_file, raxml_out))

    if os.path.exists(fasta_replaced_file):
        os.remove(fasta_replaced_file)
    if os.path.exists(phylip_file + ".reduced"):
        os.remove(phylip_file + ".reduced")
    if os.path.exists(final_output_folder + "fasta_reader_log.txt"):
        os.remove(final_output_folder + "fasta_reader_log.txt")

    swap_tree_names(tree_to_swap, final_mltree, code_name)

    if args.molecule == "prot":
        os.system("mv %s.fa %s.fa.p* %s" %
                  (args.output_dir + code_name, args.output_dir + code_name, final_output_folder))
    if args.molecule == "rrna" or args.molecule == "dna":
        os.system("mv %s.fa %s.fa.n* %s" %
                  (args.output_dir + code_name, args.output_dir + code_name, final_output_folder))
    os.system("mv %s %s %s" % (tree_taxa_list, final_mltree, final_output_folder))

    annotate_partition_tree(code_name, fasta_replace_dict, raxml_out + os.sep + "RAxML_bipartitions." + code_name)
    aa_model = find_model_used(raxml_out + os.sep + "RAxML_info." + code_name)
    update_build_parameters(args, code_name, aa_model, lowest_reliable_rank)

    sys.stdout.write("Data for " + code_name + " has been generated successfully.\n")
    terminal_commands(final_output_folder, code_name)


if __name__ == "__main__":
    main()

