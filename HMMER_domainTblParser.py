#!/usr/bin/env python3

import os
import sys
import re
import argparse
import logging
import math


def get_options():
    parser = argparse.ArgumentParser(description="Parses a domtbl file generated by HMMER, applying its own set of"
                                                 "filters and summarizing those high-quality matches."
                                                 "Optionally, sequences of the high-quality matches can also be written"
                                                 "to a FASTA file.", add_help=False)
    required_args = parser.add_argument_group("Required arguments")
    required_args.add_argument("-i",
                               dest="input",
                               help="Input domain table from HMMER to be parsed",
                               required=True)

    opt_args = parser.add_argument_group("Optional arguments")
    opt_args.add_argument("-f",
                          dest="fasta_in", required=False,
                          help="Path to a FASTA file containing the sequence that were searched against the HMM(s). "
                               "If one isn't provided, the script just prints summary stats.")
    opt_args.add_argument("-o",
                          dest="output", required=False, default="hmm_purified.fasta",
                          help="The name of the FASTA file to write containing sequences of the high-quality hits. "
                               "[default=hmm_purified.fasta]")
    opt_args.add_argument("-p",
                          dest="perc_aligned",
                          type=int,
                          default=90,
                          help="The minimum percentage of the HMM that was covered by the target sequence (ORF) "
                               "for the COG hit to be included [default=90]")
    opt_args.add_argument("-e",
                          dest="min_e",
                          type=float,
                          default=0.0001,
                          help="The largest E-value for the search to be accepted as significant [default=1E-3]")
    opt_args.add_argument("-a",
                          dest="min_acc",
                          type=float,
                          default=0.90,
                          help="The minimum acc threshold of the HMM search for reporting [default=0.90]")
    miscellaneous_opts = parser.add_argument_group("Miscellaneous options")
    miscellaneous_opts.add_argument("-v", "--verbose", action='store_true', default=False,
                                    help='Prints a more verbose runtime log')
    miscellaneous_opts.add_argument("-h", "--help",
                                    action="help",
                                    help="Show this help message and exit")
    args = parser.parse_args()
    return args


def format_hmmer_domtbl_line(line):
    stats = []
    stat = ""
    for c in line:
        if c == ' ':
            if len(stat) > 0:
                stats.append(str(stat))
                stat = ""
            else:
                pass
        else:
            stat += c
    stats.append(str(stat))
    return stats


class HmmMatch:
    def __init__(self):
        self.genome = ""  # Name of the input file (Metagenome, SAG, MAG, or isolate genome)
        self.target_hmm = ""  # Name of the HMM aligned to
        self.orf = ""  # Name of the ORF, or more generally contig sequence
        self.hmm_len = 0  # Length of the hidden Markov model
        self.start = 0  # Alignment start position on the contig
        self.end = 0  # Alignment end position on the contig
        self.pstart = 0  # Alignment start position on the hmm profile
        self.pend = 0  # Alignment end position on the hmm profile
        self.seq_len = 0  # Length of the query sequence
        self.num = 0
        self.of = 0
        self.desc = ""
        self.acc = 0.0
        self.ceval = 0.0
        self.full_score = 0

    def get_info(self):
        info_string = "Info for " + str(self.orf) + " in " + self.genome + ":\n"
        info_string += "\tHMM = " + self.target_hmm + ", length = " + str(self.hmm_len) + "\n"
        info_string += "\tSequence length = " + str(self.seq_len) + "\n"
        info_string += "\tAligned length = " + str(self.end - self.start) + "\n"
        info_string += "\tAlignment start = " + str(self.start) + ", alignment stop = " + str(self.end) + "\n"
        info_string += "\tProfile start = " + str(self.pstart) + ", profile stop = " + str(self.pend) + "\n"
        info_string += "\tNumber " + str(self.num) + " of " + str(self.of) + "\n"
        info_string += "\tcE-value = " + str(self.ceval) + "\n"
        info_string += "\tacc = " + str(self.acc) + "\n"
        info_string += "\tfull score = " + str(self.full_score) + "\n"
        return info_string


class DomainTableParser(object):

    def __init__(self, dom_tbl):
        self.alignments = {}
        self.i = 0
        self.lines = []
        self.size = 0
        try:
            self.commentPattern = re.compile(r'^#')
            self.src = open(dom_tbl)
        except IOError:
            logging.error("Could not open " + dom_tbl + " or file is not available for reading.\n")
            sys.exit(0)

    def __iter__(self):
        return self

    def read_domtbl_lines(self):
        """
        Function to read the lines in the domain table file,
        skipping those matching the comment pattern
        :return: self.lines is a list populated with the lines
        """
        line = self.src.readline()
        while line:
            comment = self.commentPattern.match(line)
            if not comment:
                self.lines.append(line.strip())
            if not line:
                break
            line = self.src.readline()
        self.size = len(self.lines)

    def next(self):
        """
        Reformat the raw lines of the domain table into
        an easily accessible hmm_domainTable format and perform
        QC to validate the significance of the alignments
        """
        if self.i < self.size:
            hit = format_hmmer_domtbl_line(self.lines[self.i])
            self.prepare_data(hit)
            self.i += 1

            try:
                return self.alignments
            except ValueError:
                return None
        else:
            self.src.close()
            return None

    def prepare_data(self, hit):
        self.alignments['query'] = str(hit[0])
        self.alignments['query_len'] = int(hit[2])
        self.alignments['hmm_name'] = str(hit[3])
        self.alignments['hmm_len'] = str(hit[5])
        self.alignments['Eval'] = float(hit[6])  # Full-sequence E-value (in the case a sequence alignment is split)
        self.alignments['full_score'] = float(hit[7])  # Full-sequence score
        self.alignments['num'] = int(hit[9])  # HMMER is able to detect whether there are multi-hits
        self.alignments['of'] = int(hit[10])  # This is the number of multi-hits for a query
        self.alignments['cEval'] = float(hit[11])  # conditional E-value
        self.alignments['pstart'] = int(hit[15])  # First position on HMM profile
        self.alignments['pend'] = int(hit[16])  # Last position on HMM profile
        self.alignments['qstart'] = int(hit[19])  # env coord from
        self.alignments['qend'] = int(hit[20])  # env coord to
        self.alignments['acc'] = float(hit[21])
        self.alignments['desc'] = ' '.join(hit[22:])


def detect_orientation(q_i, q_j, r_i, r_j):
    if q_i <= r_i <= q_j:
        if q_i <= r_j <= q_j:
            return "supersequence"
        else:
            return "overlap"
    elif r_i <= q_i <= r_j:
        if r_i <= q_j <= r_j:
            return "subsequence"
        else:
            return "overlap"
    else:
        return "satellite"


def scaffold_subalignments(fragmented_alignment_data):
    """
    If one or more alignments do not completely redundantly cover the HMM profile,
    overlap or are within a few BPs of each other of the query sequence,
    and do not generate an alignment 120% longer than the HMM profile,
                                                THEN
    merge the alignment co-ordinates, average the acc, Eval, cEval and change 'num' and 'of' to 1
                                            Takes this:
    -------------
                --------------
                                                            --------------------------------------
                                 ----------------
                                        and converts it to:
    ---------------------------------------------           --------------------------------------
    :return:
    """
    # Since we're dealing with HMMs, its difficult to estimate the sequence length variance
    # so we're allowing for some 'wobble' in how long or short paralogs could be
    seq_length_wobble = 1.2
    accepted_states = ["overlap", "satellite"]
    i = j = 0
    while i < len(fragmented_alignment_data):
        base_aln = fragmented_alignment_data[i]
        while j < len(fragmented_alignment_data):
            if j != i:
                projected_aln = fragmented_alignment_data[j]
                # Check for sub- or super-sequence orientation on the query sequence
                q_orientation = detect_orientation(base_aln.start, base_aln.end,
                                                   projected_aln.start, projected_aln.end)
                # Check for redundant profile HMM coverage
                p_orientation = detect_orientation(base_aln.pstart, base_aln.pend,
                                                   projected_aln.pstart, projected_aln.pend)
                a_new_start = min([base_aln.start, projected_aln.start])
                a_new_end = max([base_aln.end, projected_aln.end])
                if q_orientation in accepted_states and p_orientation in accepted_states:
                    if float(a_new_end - a_new_start) < float(seq_length_wobble * int(base_aln.hmm_len)):
                        base_aln.start = a_new_start
                        base_aln.end = a_new_end
                        base_aln.pstart = min([base_aln.pstart, projected_aln.pstart])
                        base_aln.pend = max([base_aln.pend, projected_aln.pend])
                        if base_aln.num > 1:
                            base_aln.num = min([base_aln.num, projected_aln.num])
                        base_aln.of -= 1
                        base_aln.ceval = min([base_aln.ceval, projected_aln.ceval])
                        fragmented_alignment_data.pop(j)
                        j -= 1
                else:
                    pass
            j += 1
        i += 1
        # # For debugging:
        # for aln in fragmented_alignment_data:
        #     aln.print_info()
    return fragmented_alignment_data


def orient_alignments(fragmented_alignment_data):
    alignment_relations = dict()
    i = 0
    j = 0
    while i < len(fragmented_alignment_data):
        initial_start = fragmented_alignment_data[i].start
        initial_stop = fragmented_alignment_data[i].end
        while j < len(fragmented_alignment_data):
            if j != i:
                alignment_relations[(i, j)] = detect_orientation(initial_start,
                                                                 initial_stop,
                                                                 fragmented_alignment_data[j].start,
                                                                 fragmented_alignment_data[j].end)
            j += 1
        j = i
        i += 1
    return alignment_relations


def consolidate_subalignments(fragmented_alignment_data, alignment_relations, distinct_alignments):
    alignments_to_defecate = set()
    for pair in alignment_relations:
        # If there are multiple alignments that span the whole hmm profile, report them both
        base, projected = pair
        if alignment_relations[pair] == "satellite":
            pass
        elif alignment_relations[pair] == "overlap":
            # If there are multiple overlapping alignments on the same query, take the one with the lowest E-value
            if fragmented_alignment_data[base].ceval < fragmented_alignment_data[projected].ceval:
                alignments_to_defecate.add(projected)
            else:
                alignments_to_defecate.add(base)
        elif alignment_relations[pair] == "supersequence":
            alignments_to_defecate.add(projected)
        elif alignment_relations[pair] == "subsequence":
            alignments_to_defecate.add(base)
        else:
            sys.stderr.write("ERROR: Unexpected alignment comparison state: '" + alignment_relations[pair] + "'\n")
            sys.exit(31)
    x = 0
    # Filter out the worst of the overlapping alignments that couldn't be scaffolded
    while x < len(fragmented_alignment_data):
        if x not in alignments_to_defecate:
            hmm_match = fragmented_alignment_data[x]
            query_header_strand = ' '.join([hmm_match.orf, hmm_match.desc]) + \
                                  '_' + str(hmm_match.num) + '_' + str(hmm_match.of)
            distinct_alignments[query_header_strand] = hmm_match
        x += 1

    return distinct_alignments


def format_split_alignments(domain_table, num_fragmented, glued, multi_alignments, raw_alignments):
    """
    Handles the alignments where 'of' > 1
    If the alignment covers the whole target HMM or if the distance between the two parts of the alignment
    are very far apart, then the alignment will be divided into two unrelated alignments
    If the alignment parts are near together and/or each part covers a portion of the HMM, then they will be joined
    :param num_fragmented: Accumulator for the number of HMM alignments with greater than 1 sub-alignments ('of')
    :param glued:
    :param multi_alignments: Accumulator for the number of query sequences with alignments to >1 HMM profiles
    :param raw_alignments: Accumulator for the number of alignments in all domain tables
    :param domain_table: DomainTableParser() object
    :return:
    """
    # Dictionary of single sequence alignments to return
    distinct_alignments = dict()

    # Query-relevant parsing variables
    split_query_name = ""
    previous_hmm_target = ""
    previous_query_header = ""
    fragmented_alignment_data = list()
    while domain_table.next():
        data = domain_table.alignments
        hmm_match = HmmMatch()
        hmm_match.target_hmm = data['hmm_name']
        hmm_match.hmm_len = data['hmm_len']
        hmm_match.seq_len = data['query_len']
        hmm_match.orf = data['query']
        hmm_match.desc = data['desc']
        hmm_match.start = data['qstart']
        hmm_match.end = data['qend']
        hmm_match.pstart = data['pstart']
        hmm_match.pend = data['pend']
        hmm_match.num = data['num']
        hmm_match.of = data['of']
        hmm_match.acc = data['acc']
        hmm_match.ceval = data['cEval']
        hmm_match.full_score = data['full_score']

        raw_alignments += 1
        # Finish off "old business" (sub-alignments)
        if split_query_name != data["query"] and len(fragmented_alignment_data) > 0:
            num_fragmented += 1
            # STEP 1: Scaffold the alignments covering overlapping regions on the query sequence
            before_scaffolding = len(fragmented_alignment_data)
            scaffolded_alignment_data = scaffold_subalignments(fragmented_alignment_data)
            if before_scaffolding != len(fragmented_alignment_data):
                glued += (before_scaffolding - len(fragmented_alignment_data))

            # STEP 2: Determine the order and orientation of the alignments
            alignment_relations = orient_alignments(scaffolded_alignment_data)

            # STEP 3: Decide what to do with the fragmented alignments: join or split?
            distinct_alignments = consolidate_subalignments(fragmented_alignment_data,
                                                            alignment_relations,
                                                            distinct_alignments)
            fragmented_alignment_data.clear()

        # Carry on with this new alignment
        query_header_desc_aln = ' '.join([hmm_match.orf, hmm_match.desc]) + \
                                '_' + str(hmm_match.num) + '_' + str(hmm_match.of)
        query_header = ' '.join([hmm_match.orf, hmm_match.desc])
        if not hmm_match.orf:
            logging.error("Double-line parsing encountered: hmm_match.orf is empty!\n")
            sys.exit(9)

        if hmm_match.target_hmm != previous_hmm_target and query_header == previous_query_header:
            # New HMM (target), same ORF (query)
            multi_alignments += 1

        if data["of"] == 1:
            distinct_alignments[query_header_desc_aln] = hmm_match
        else:
            split_query_name = hmm_match.orf
            fragmented_alignment_data.append(hmm_match)

        previous_query_header = query_header
        previous_hmm_target = hmm_match.target_hmm

    # Check to see if the last alignment was part of multiple alignments, just like before
    if len(fragmented_alignment_data) > 0:
        num_fragmented += 1
        scaffolded_alignment_data = scaffold_subalignments(fragmented_alignment_data)
        alignment_relations = orient_alignments(scaffolded_alignment_data)
        distinct_alignments = consolidate_subalignments(fragmented_alignment_data,
                                                        alignment_relations,
                                                        distinct_alignments)

    return distinct_alignments, num_fragmented, glued, multi_alignments, raw_alignments


def filter_poor_hits(args, distinct_alignments, num_dropped):
    """
    Filters the homology matches based on their E-values and mean posterior probability of aligned residues from
    the maximum expected accuracy (MEA) calculation.
    Takes into account multiple homology matches of an ORF to a single gene and determines the total length of the
    alignment instead of treating them as individual alignments. This information is used in the next filtering step.
    """
    min_acc = float(args.min_acc)
    min_e = float(args.min_e)

    purified_matches = dict()

    for query_header_desc_aln in sorted(distinct_alignments):
        hmm_match = distinct_alignments[query_header_desc_aln]

        query_header_desc = (hmm_match.orf, hmm_match.desc)
        if query_header_desc not in purified_matches:
            purified_matches[query_header_desc] = list()

        if hmm_match.acc >= min_acc and hmm_match.ceval <= min_e:
            purified_matches[query_header_desc].append(hmm_match)
        else:
            num_dropped += 1

    return purified_matches, num_dropped


def filter_incomplete_hits(args, purified_matches, num_dropped):
    complete_gene_hits = list()

    for query in purified_matches:
        for hmm_match in purified_matches[query]:
            ali_len = hmm_match.pend - hmm_match.pstart
            perc_aligned = (float((int(ali_len)*100)/int(hmm_match.hmm_len)))
            if perc_aligned >= args.perc_aligned:
                complete_gene_hits.append(hmm_match)
            else:
                num_dropped += 1

    return complete_gene_hits, num_dropped
