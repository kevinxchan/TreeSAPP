import pytest
import unittest
import os
import argparse

import sys, inspect
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))))
import fasta

TEST_DATA_PATH='/home/travis/build/hallamlab/TreeSAPP/tests/test_data'


def create_parser(treesapp, targets, reftree):
    args = argparse.Namespace()
    args.alignment_mode = 'd'
    args.reftree = reftree
    args.targets = [targets]
    args.treesapp = treesapp
    args.check_trees = False
    args.fasta_input = 'test_data/marker_test_suite.faa'
    args.output = '/home/travis/build/hallamlab/marker_test/'
    args.output_dir_var = '/home/travis/build/hallamlab/marker_test/various_outputs'
    args.skip = 'n'
    args.molecule = 'prot'
    args.executables = {'BMGE.jar': '/home/travis/build/hallamlab/TreeSAPP/sub_binaries/BMGE.jar', 'hmmalign': '/usr/bin/hmmalign', 'usearch': '/home/ace/github/TreeSAPP/sub_binaries/usearch', 'hmmsearch': '/usr/bin/hmmsearch', 'trimal': '/usr/bin/trimal', 'raxmlHPC': '/usr/bin/raxmlHPC', 'hmmbuild': '/usr/bin/hmmbuild', 'prodigal': '/usr/local/bin/prodigal', 'papara': '/usr/bin/papara'}
    args.reference_data_prefix=''
    args.num_threads = 3
    args.output_dir_final = '/home/ace/marker_test/final_outputs/'
    args.formatted_input_file = ''
    args.composition = 'meta'
    args.overwrite = True
    args.delete = False
    args.reclassify = False
    args.min_e = 0.0001
    args.min_acc = 0.7
    args.min_likelihood = 0.2
    args.min_seq_length = 30
    args.perc_aligned = 15

    return args

def short_fasta():
    fasta_file = TEST_DATA_PATH + '/short_fasta.fa'
    return fasta_file, open(fasta_file, 'r')

results = [('213_McrA', 'M---------------------------------------------------------------------------------------------------------------------------------------------------------------AKKIEKTQKLFLKALKEKFA-------------EDPQS--TSTIFAREGLKQS--PRKMEFVKAGNAAA-MSR--GLSMYDPVRCHI---GGIPLGQRQLMTYEVSGT-G---------------------VFVEGDDLHFVNNAAMQQMWDDIRRTILVNMDLAHQTLQKRLGKEVTPETINEFLHVVNHAMPGA-AVVQEHMVETHPSLVDDCYVKVFTGDDELADDLEPQFVINVEKLFPG------K-QA----AQLKAAVGKSLWQAIRIPTIVSRTCDGGTTSRWSAMQLGMSFIGAYHMCAGEAATADLAYAAKHAGVIQMAE-ILPARRARGPNEPGGIKFGHFADMVQT-DRKYPH-----------------DPAKASLEVV-AAGTMLFDQIWLGSYMSGG-VGFTQ-YATAAYTDNILDDYTYYGMDY-IKDKYKVDWKNPG-EKDKV-KP-TQEVVNDIASE-VTLYGMEQYEQFPTALETHFGGSQRASVLAAASGLSTAIATGNSNAGLNGW-YLSMLLHKEGWSRLGFYGYDLQDQCGSANTESYRADEGCVGELRGANYPNYAMNVGHQGEYAAIAGAAHITRGDAWALNPLIKIAFADP-SLKFDFSEPRREFAKGAIREF-MPAGERALIIP-AR-----------------------'), ('214_McrA','----------------------------------------------------------------------------------------------------------------------------------------------------------------MAKIERTQKLFLKSLKEKFA------------G-DPTG-TTASYFTFGDMKQS--PRKMEFLEQGRRVS-MDR--GISQYDPRRAHL---GGIPLGQRQLMTYEVSTT-G---------------------VFVEGDDLHFVNNSAMQQCWDDIRRTVIVGMDLAHQTLQKRLGKEVTPETINEYLHVLNHAMPGA-AVVQEHMVETAPALVDDCYVKVFSGDDELVDDLEPQFVLNVDKLFPA------K-QA----EGLKAAVGKSLWQAVHIPTTVSRTCDGGTTSRWSAMQLGMSYIAAYRMCAGEAAVADLSFAAKHAGVIQMAS-HLPARRARGPNEPGGIGFGLFSDIIQA-NRKYPN-----------------DPARASLEVV-AAGTMLFDQIWLGSYMSGG-VGFTQ-YATAAYTDNILDEYTYYGMDY-LKDKYKVDWKNPS-PADRV-KA-SQDIVNDLATE-VSLNAMEQYEQFPTLMEDHFGGSQRAGVIAAACGLTCSIGTGNSNAGLNGW-YLSMLLHKEGWSRLGFFGYDLQDQCGSTNSLSIRPDEGAMGEVRGPNYPNYAMNVGHQGEYAAIVGGAHYGRGDGWCFDPRVAITFADP-ALKFDFAEPRREFAKGAIREF-MPAGERSLIIP-AR-----------------------')]

class FastaTests(unittest.TestCase):

    def test_read_fasta_to_dict(self):
        fasta_file, fasta_handler = short_fasta()
        assert(fasta.read_fasta_to_dict(fasta_file) == {results[0][0]: results[0][1], results[1][0]:results[1][1]})

        with pytest.raises(SystemExit) as pytest_wrapped_e:
            fasta.read_fasta_to_dict(' ')
            assert pytest_wrapped_e.type == SystemExit
            assert pytest_wrapped_e.value.code == 5
                                                            
    def test_generate_fasta(self):
        fasta_file, fasta_handler = short_fasta()
        i = 0;
        for record in fasta.generate_fasta(fasta_handler):
            assert(record == results[i])               
            i+=1
    

    def test_format_read_fasta(self):
        args = create_parser('/home/ace/github/TreeSAPP/', 'M0701', 'p')
        args.fasta_input = 'tests/test_data/short_fasta_valid.faa'
        formatted_fasta_dict = fasta.format_read_fasta(args.fasta_input, "prot", args.output)
        assert('>k127_1003429_914638_1_#_2_#_1513_#_1_#_ID=914638_1_partial=10_start_type=Edge_rbs_motif=None_rbs_spacer=None' in formatted_fasta_dict.keys())
        assert('>k127_35937_flag_381292_3_#_288_#_416_#_-1_#_ID=381292_3_partial=01_start_type=Edge_rbs_motif=None_rbs_spacer' in formatted_fasta_dict.keys())
        assert( '>Prodigal_Seq_6_6_3_#_3683_#_4678_#_-1_#_ID=6_3_partial=00_start_type=ATG_rbs_motif=None_rbs_spacer=None_nosZ' in formatted_fasta_dict.keys())
      

    def test_get_headers(self):
       ref_headers = fasta.get_headers(TEST_DATA_PATH + '/short_fasta.fa')
       assert(ref_headers == ['>213_McrA', '>214_McrA'])

       with pytest.raises(SystemExit) as pytest_wrapped_e:
             fasta.get_headers('')
             assert pytest_wrapped_e.type == SystemExit
             assert pytest_wrapped_e.value.code == 5

    def test_generate_fasta(self):
        assert(True)

    def test_write_new_fasta(self):
        assert(True)

    def test_get_header_format(self):
        assert(True)

    def test_deduplicate(self):
        fasta_dict = fasta.read_fasta_to_dict(TEST_DATA_PATH + "/dup_fasta.fa")
        fasta_dict = fasta.deduplicate_fasta_sequences(fasta_dict)

        for i in range(0, len(results)):
            assert(results[i][0] in fasta_dict.keys())
            assert(results[i][1] in fasta_dict.values())

        
        fasta_dict = fasta.read_fasta_to_dict(TEST_DATA_PATH + "/short_fasta.fa")
        fasta_dict = fasta.deduplicate_fasta_sequences(fasta_dict)

        for i in range(0, len(results)):
            assert(results[i][0] in fasta_dict.keys())
            assert(results[i][1] in fasta_dict.values())

