### This is used in the case it is a new description not seen before
import pandas as pd
import re
import numpy as np
from collections import defaultdict
from sqlalchemy import create_engine
import sqlite3
import fuzzy
import nltk
import numpy

class description_parser():
    """Provides common code for parsing expenditure description"""

    def __init__(self,conn,last_load_id):
        self.conn = conn
        self.last_load_id = last_load_id

    def is_company_check(self,comp_descr):
        """Check if company description string passed is just numeric

        Parameters
        ----------
        comp_descr : string
            Containing company description from statement.

        Attributes
        ----------
        num_chk : bool
            True if comp_descr contains more than one string or has letters.
            False if comp_descr is just numbers.
        """
        num_chk = True
        numeric = re.findall('[0-9]+',comp_descr)
        if len(numeric) > 0:
             num_chk = (numeric[0] != comp_descr)
        return num_chk

    def word_tokenizer(self, comp_descr):
        components = re.findall('[\w0-9&]+',comp_descr.lower())
        return components

    def comp_word_parser(self,comp_descr,frequency_stats):
        """Tags each word in a description with features of the word to
        help determine if the word is actually a word

        It takes a description string and splits it into individual words
        based on the whitespace or a set of special characters.

        Each word is individually analysed and a series of tags attributed
        to it, which are used with the comp_name_score function to determine
        the likelihood of the word being a word:
        - Is the word in the dictionary, NLTK dictionary is used.
        - Is part of the word (word length>3) in the dictionary.
        - Phonetic representation of the word (using double metaphone algorithm)
        - Vowel and consannat counts.  A heuristic is added for words, if the
        word has 1<vowels & consannants>vowels then the word_struc is returned as
        True.
        - Frequency count, a table in the database records the frequency count
        of words occuring in the description.
        - Parts of speech, for the word, this is currently not exploited in the
        word definition but oculd be integrated later.

        Parameters
        ----------
        comp_descr : string
            Containing company description from statement.

        Attributes
        ----------
        tags_ : dict
            A dictionary containing tags for each word int the description
            [is_word_term,embedded_word, word_struc,prev_count,pos,
            word_phon_count]
        """
        tag_comp = {}
        word_dict = set([i.lower() for i in nltk.corpus.words.words()])
        vowels = set(['a','e','i','o','u','y'])

        # Add phonetic term for whole description
        dmetaphone = fuzzy.DMetaphone(3)
        phon = dmetaphone(comp_descr)

        # Split company description into tokens
        components = self.word_tokenizer(comp_descr)
        word_comp = dict()
        # Now tag the components
        for each in components:
            # Check if in dictionary
            if each in word_dict:
                is_word_term = 2
            else:
                is_word_term = 0
            # Check if part of word is in dictionary if <3 letters
            word_len = len(each)
            embedded_word = False
            if is_word_term > 0:
                embedded_word = True
            elif (word_len > 3):
                for i in range(3,word_len):
                    word_part = each[:i]
                    if word_part in word_dict:
                        embedded_word = True
            else:
                embedded_word = False
            # Phonetic count
            phon_word1,phon_word2 = dmetaphone(each)
            sound_count1 = 0
            sound_count2 = 0
            if phon_word1 != None:
                sound_count1 = int(self.phon_frequency_retriever(phon_word1))
                sound_count1 = (sound_count1 - frequency_stats.phon_mean_)/frequency_stats.phon_std_
            elif phon_word2 != None:
                sound_count2 = int(self.phon_frequency_retriever(phon_word2))
                sound_count2 = (sound_count2 - frequency_stats.phon_mean_)/frequency_stats.phon_std_
            word_phon_count = max(sound_count1,sound_count2)
            # Vowels and consanants
            struc = []
            v_count = 0
            c_count = 0
            word_struc = False
            for letter in each:
                if letter in vowels:
                    struc.append('v')
                    v_count += 1
                else:
                    struc.append('c')
                    c_count += 1
            # Check pattern of V & C
            if v_count > 1:
                if c_count >= v_count:
                    word_struc = True
            else:
                word_struc = False
            # Frequency term has occured before
            prev_count = self.frequency_retriever(each)
            prev_count = (prev_count - frequency_stats.word_mean_)/frequency_stats.word_std_
            if prev_count < 0:
                prev_count = 0
            # Length of word
            len_word_points = 0
            if len(each) > 5:
                len_word_points = 1
            # Parts of Speech
            pos = nltk.pos_tag([each])[0][1]

            word_comp[each] = [is_word_term,embedded_word, word_struc,prev_count,pos, word_phon_count,len_word_points]

        tag_comp[comp_descr] = word_comp
        self.tags_ = tag_comp
        return tag_comp

    def comp_name_score(self,comp_descr,frequency_stats):
        """Gives a score for each word in a description for likelihood of
        being part of the companies name

        The strategy gives a word score based on the tags returned from
        comp_word_parser.  1 point is given by a True statement and currenlty
        the prev_word count is used in raw form.

        Parameters
        ----------
        comp_descr : string
            Containing company description from statement.

        Attributes
        ----------
        name_scores : dict
            A score attributed to each word of the description based on
            likeliness of being part of the companies name.

        """
        tag_comp = self.comp_word_parser(comp_descr,frequency_stats)
        name_scores = defaultdict(dict)
        for word, word_score in tag_comp[comp_descr].items():
            score = 0
            for value in word_score:
                if type(value) == bool:
                    if value == True:
                        score += 1
                elif (type(value) == int) or (type(value) == np.float64):
                    score += value
            name_scores[comp_descr][word] = score
            self.name_scores = name_scores
        return name_scores

    def company_name_full(self,comp_descr,frequency_stats):
        """Predicted company name evaluator

        Based on an initial description for a transaction will
        return the predicted company name.
        Based on the word scores returned from comp_name_scores
        a prediction is made as to the name of the company.
        If the score of the word returned is >3 then it is deemed
        to be part of the name of the company

        Parameters
        ----------
        comp_descr : string
            Containing company description from statement.

        Attributes
        ----------
        comp_name_full : string
            Predicted company name in full
        """

        accepted_parts = ['&','and','the']
        name_scores = self.comp_name_score(comp_descr,frequency_stats)

        comp_keys = self.word_tokenizer(comp_descr)
        if len(comp_keys) == 1:
            company = comp_keys[0]
            return company
        else:
            comp_part_name = []
            for part in comp_keys:
                part = part.lower()
                score = name_scores[comp_descr].get(part,0)
                if part in accepted_parts:
                    comp_part_name.append(part)
                elif score >= 3:
                    comp_part_name.append(part)
            comp_name_full = ' '.join(comp_part_name)
            return comp_name_full

    def comp_full_details(self,comp_descr,frequency_stats):
        """Returns a full list of parameters based on the companies predicted
        name to disambiguate it from similar names

        The function inserts a company name produced from company_name_full
        into the SQL database along with details of the:
        - Phonetics of the first word
        - The first letter of the company
        - The set of unique letters of the companies name

        Parameters
        ----------
        comp_descr : string
            Containing company description from statement.

        Attributes
        ----------
        returns : dict
            (company,phon_match1,phon_match2,first_letter,letter_set)
        """

        detail_dict = {}
        company = self.company_name_full(comp_descr,frequency_stats)
        dmetaphone = fuzzy.DMetaphone(3)
        phon_match1,phon_match2 = dmetaphone(company)
        if len(company) == 0:
            letter_set = set()
            first_letter = ''
        else:
            letter_set = set(re.findall('[\w0-9]',company.split()[0]))
            first_letter = company[0]
        return (comp_descr,company,phon_match1,phon_match2,first_letter,str(letter_set))

    def company_insert(self,comp_descr,frequency_stats):
        """Inserts new company with name attributes into SQL table

        Parameters
        ----------
        comp_descr : string
            Containing company description from statement.
        """

        company_tags = self.comp_full_details(comp_descr,frequency_stats)

        sql_st = '''
            INSERT OR REPLACE INTO comp_name_compare(
            description,company_lst_name,phonetic1,phonetic2,first_letter,set_letters)
            VALUES(?,?,?,?,?,?)
        '''
        cur = self.conn.cursor()
        cur.execute(sql_st,company_tags)
        self.conn.commit()

    def company_name_update(self):
        """To be finished, placeholder for moment"""

        similar_dict = {}
        accro_dict = defaultdict()
        sql_st_fetch = """
        SELECT *
        FROM comp_name_compare;
        """

        cur = self.conn.cursor()
        comp_param_list = cur.execute(sql_st_fetch).fetchall()

        for i in range(len(comp_param_list)):
            comp_0 = comp_param_list[i][0]
            phon_0 = set([comp_param_list[i][2],comp_param_list[i][3]])
            first_letter_0 = comp_param_list[i][4]
            letter_set_0 = set(re.findall("\'([a-z0-9])\'",comp_param_list[i][5]))
            similar_dict[comp_0] = []
            accro_dict[comp_0] = []
            for j in range(len(comp_param_list)):
                match_count = 0
                if j != i:
                    comp_1 = comp_param_list[j][0]
                    phon_1 = set([comp_param_list[j][2],comp_param_list[j][3]])
                    first_letter_1 = comp_param_list[j][4]
                    letter_set_1 = set(re.findall("\'([a-z0-9])\'",comp_param_list[j][5]))
                    if len(phon_0 - phon_1) < 2:
                        match_count += 1
                    if first_letter_0 == first_letter_1:
                        match_count += 1
                    if len(letter_set_0) < len(letter_set_1):
                        if len(letter_set_0 - letter_set_1) == 0:
                            match_count += 1
                    else:
                        if len(letter_set_1 - letter_set_0) == 0:
                            match_count += 1
                else:
                    match_count = -1

                if match_count >= 3:
                    accro_dict[comp_0].append(comp_1.lower())
                elif match_count == -1:
                    accro_dict[comp_0].append(comp_param_list[i][1].lower())

        """ Accronym maker """
        accro_transform = {}
        for comp_name,derivatives in accro_dict.items():
            #names_lst = derivatives + [comp_name]
            if len(derivatives) > 1:
                gen_name = max(derivatives,key=len).split()[0]
            else:
                gen_name = derivatives[0]
            accro_transform[comp_name] = gen_name
            comp_tuple = (comp_name,gen_name)
            sql_st = '''
                INSERT OR REPLACE INTO general_name_table
                (company_lst_name,general_name)
                VALUES(?,?)
            '''
            cur = self.conn.cursor()
            cur.execute(sql_st,comp_tuple)
            self.conn.commit()

    def frequency_updater(self,comp_descr):
        """Updates database with word occurence frequency

        Parameters
        ----------
        comp_descr : string
            Containing company description from statement.
        conn : db_connection
            SQLITE database connection
        """
        components = self.word_tokenizer(comp_descr)

        cur = self.conn.cursor()

        for word in components:
            # Update phonetics table
            dmetaphone = fuzzy.DMetaphone(3)
            phon = dmetaphone(word)
            if phon[0] != None:
                phon = phon[0]
            else:
                phon = phon[1]
            sql_st1 = """
                INSERT OR IGNORE INTO comp_word_counts VALUES (?,?);
            """
            sql_st2 = """
                UPDATE comp_word_counts
                 SET frequency = frequency + 1
                WHERE comp_term = (?);
            """
            sql_phon1 = """
                INSERT OR IGNORE INTO comp_phon_counts VALUES (?,?);
            """
            sql_phon2 = """
                UPDATE comp_phon_counts
                 SET frequency = frequency + 1
                WHERE comp_phon = (?);
            """

            data = (word,0)
            data_phon = (phon,0)
            cur.execute(sql_st1,data)
            cur.execute(sql_phon1,data_phon)
            cur.execute(sql_st2,(word,))
            cur.execute(sql_phon2,(phon,))
        self.conn.commit()

    def frequency_retriever(self,word):
        """Retrieves word occurence frequency

        Parameters
        ----------
        comp_descr : string
            Containing company description from statement.

        Attributes
        ----------
        freq : int
            frequncy of individual word
        """
        cur = self.conn.cursor()
        sql_st = """
            SELECT frequency
            FROM comp_word_counts
            WHERE comp_term = ?;
        """

        freq = cur.execute(sql_st,(word,)).fetchall()[0][0]
        self.freq = freq
        return freq

    def frequency_stats(self):
        """Retrieves the mean and std. deviation for phonetic and word occurence

        Attributes
        ----------
        word_mean : real
            mean frequency occurence for a word
        phon_mean : real
            mean frequency occurence for a phonetic
        word_var : real
            variance of word frequencies
        phon_var : real
            variance of phonetic frequency
        """
        df_phon = pd.read_sql_query('SELECT frequency FROM comp_phon_counts',self.conn)
        df_phon = pd.to_numeric(df_phon.frequency)

        phon_mean = df_phon.mean()
        phon_std = df_phon.std()

        df_word = pd.read_sql_query('SELECT frequency FROM comp_word_counts',self.conn)
        df_word = pd.to_numeric(df_word.frequency)

        word_mean = df_word.mean()
        word_std = df_word.std()

        self.phon_mean_ = phon_mean
        self.word_mean_ = word_mean
        self.phon_std_ = phon_std
        self.word_std_ = word_std

        return self

    def phon_frequency_retriever(self,phon):
        """Retrieves phonetic occurence frequency for a word

        Parameters
        ----------
        phon : string
            Containing phoetic to search for frequency.

        Attributes
        ----------
        freq : int
            frequncy of phonetic term
        """
        cur = self.conn.cursor()
        sql_st = """
            SELECT frequency
            FROM comp_phon_counts
            WHERE comp_phon = ?;
        """

        freq = cur.execute(sql_st,(phon,)).fetchall()[0][0]
        self.freq = freq
        return freq

    def final_table():
        """SQL script for joining expenditure data to general company name"""

        cur = self.conn.cursor()
        sql_st = '''
            SELECT (yr,mnth,dy,reference,account_name, currency,
                company,comp_type,country,city,lat,lng,expenses_raw.value)
            FROM expenses_raw
            JOIN general_name_table ON general_name_table.company_lst_name = expenses_raw.description
        '''

    def updater(self,company_name_lst):
        """Primary code to run all procedures to update comp_name database

        Parameters
        ----------
        comp_descr : string
            Containing company description from statement.
        """
        for comp_descr in company_name_lst:
            num_chk = self.is_company_check(comp_descr)
            if num_chk:
                self.frequency_updater(comp_descr)

        # Get statistics
        frequency_stats = self.frequency_stats()

        for comp_descr in company_name_lst:
            num_chk = self.is_company_check(comp_descr)
            if num_chk:
                self.company_insert(comp_descr,frequency_stats)
