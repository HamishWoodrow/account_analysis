import numpy as np
import urllib
import json
import sqlite3

class company_type():
    """Module to get the company type from geo location and company name

        Parameters
        ----------
        conn : sqlite3 db connection
            SQLITE database connection
    """

    def __init__(self,conn):
        self.conn = conn

    def defined_companies(self):
        """Creates a list of previously defined companies

        SQL select of full table (defined_company_types), which
        contains a list company names and predefined company.
        The list of dfined companies are returned as a dictionary
        with key as the description and a list containing the proper
        company name and the type as the second entry in the list.

        returns self
        """

        sql_st = '''
            SELECT *
            FROM defined_company_types
        '''
        cur = self.conn.cursor()
        defined_types = cur.execute(sql_st).fetchall()
        defined_comp_types = dict()
        for record in defined_types:
            defined_comp_types[record[1]] = [record[2],record[3]]

        self.comp_types_ = defined_comp_types

        return self

    def google_search(self,comp_name,lat,lng):
        """Google places API request for single company

        The module takes the company along with the Latitude and longitude
        of the user on the day of the transaction and then creates a google
        search query for that company and location.  Google then responds
        with a json giving the top 20 matches for the query.  For each
        response a company type is returned.
        A search radius of 5000 m is used for matching the company name.
        If no matches are found then an empty dictionary is returned.

        Details of the api can be found at:
            https://developers.google.com/places/web-service/search

        Parameters
        ----------
        comp_name : string
            Predicted company name based on the description
        lat : float
            Latitude of user for the day of the transaction
        lng : float
            Longitude of user for the day of the transaction

        Attributes
        ----------
        goog_details : dict
            Containing the results from the query.
        """

        prefixhtml = 'https://maps.googleapis.com/maps/api/place/textsearch/json?query='

        API_key = 
        descrip = comp_name.replace(' ','+')
        lat = str(lat)
        lng = str(lng)
        radius = '5000'
        query =('%s&location=%s,%s&radius=%s&key=%s') % (descrip,lat,lng,radius,API_key)

        url = prefixhtml + query
        page = urllib.urlopen(url)
        data = page.read()
        js = json.loads(data)
        try:
            goog_details = js['results']
        except:
            goog_details = []

        return goog_details

    def company_type(self,comp_name,lat,lng):
        """Module returns the company type given the company name and location

        The module checks if the company name is in the defined company
        name table, if it is not then a the google_search function is run
        in order to construct a search query using google api, to find the
        comapany type by sending the location of the user the day of the
        transaction.

        Parameters
        ----------
        comp_name : string
            Predicted company name based on the description
        lat : float
            Latitude of user for the day of the transaction
        lng : float
            Longitude of user for the day of the transaction

        Attributes
        ----------
        goog_details : dict
            Containing the resultsfor the company type.
        """

        dc = self.defined_companies()

        comp_type = ''
        goog_details = []
        if comp_name != None:
            for company,tags in dc.comp_types_.items():
                if company in comp_name:
                    comp_type = tags[1]

            goog_details = [comp_type]

            # if not part of the  company list, then use google api
            if len(comp_type) == 0:
                goog_details=self.google_search(comp_name,lat,lng)

        return goog_details

    def data_retriever(self):
        """For each transaction, finds the type based on company name and location

        SQL select from the geo_expense_data table, for each transaction
        the company type is launched.  If the response is from a google
        query, then each result of possible companies matching the query
        is evaluated based on the distance between visited locations on
        on that day.  This is to select the right company, in case of
        multiples (i.e. Starbuck's coffee in a city).

        This takes the full location history for the user on the given day
        of the transaction and calculates the distance between those locations
        and the locations of the companies given by the google search query.

        Then once the distance between every location visited on a given day
        and the list of possible matching locations is evaluataed, the entry
        with the smallest distance is chosen as the company that the transaction
        took place at.
        """

        sql_st = '''
            SELECT *
            FROM geo_expense_data
        '''
        cur = self.conn.cursor()
        geo_comp_data = cur.execute(sql_st).fetchall()

        for record in geo_comp_data:
            geo_expense_id = record[0]
            year = record[2]
            month = record[3]
            day = record[4]
            comp_name = record[5]
            country = record[6]
            city = record[7]
            state = record[9]
            lat = record[11]
            lng = record[12]
            goog_details = self.company_type(comp_name,lat,lng)

            locations = self.locations_visited(year,month,day)
            # Find distance matrix between locations and visited places
            # Generate matrix n_location by n_goog_records
            # Should probably look to add some heuristic for name match
            if len(goog_details) == 0:
                sql_record = (geo_expense_id,'','','','','','')
            elif type(goog_details[0]) == dict:
                dist_array = np.zeros((len(locations),len(goog_details)))
                for i in range(len(locations)):
                    loc_lat = locations[i][0]
                    loc_lng = locations[i][1]
                    for j in range(len(goog_details)):
                        goog_lat = goog_details[j]['geometry']['location']['lat']
                        goog_lng = goog_details[j]['geometry']['location']['lng']

                        dist_array[i,j] = self.distance(goog_lat,goog_lng,loc_lat,loc_lng)

                min_dist_idx = np.argmin(dist_array)
                m = min_dist_idx // dist_array.shape[1]
                n = min_dist_idx - dist_array.shape[1] * m
                comp_type = goog_details[n]['types'][0]
                goog_name = goog_details[n]['name']
                address = goog_details[n]['formatted_address']
                placeid = goog_details[n]['place_id']
                goog_lat = goog_details[n]['geometry']['location']['lat']
                goog_lng = goog_details[n]['geometry']['location']['lng']

                sql_record = (geo_expense_id,goog_name,comp_type,address,placeid,goog_lat,goog_lng)
            else:
                comp_type = goog_details[0]
                sql_record = (geo_expense_id,'',comp_type,'','','','')

            self.data_writer(sql_record)

    def locations_visited(self,year,month,day):
        """Returns the latitude and longitude for a user on a given day

        SQL select statement for table goog_locations, which returns
        the latitude and longitude of all places visited
        by user for that day.

        Parameters
        ----------
        year : int
        month : int
        day : int

        Attributes
        ----------
        locations : list
            A list of tuples containing every recorded location of the user
            for the day requested.
        """

        sql_st = '''
            SELECT lat, lng
            FROM goog_locations
            WHERE
                (goog_locations.yr = ?) and
                (goog_locations.mnth = ?) and
                (goog_locations.dy = ?)
        '''

        cur = self.conn.cursor()
        locations = cur.execute(sql_st,(year,month,day)).fetchall()

        return locations

    def distance(self,goog_lat,goog_lng,loc_lat,loc_lng):
        """Calculates euclidean distance based on two coordinate positions

        Calculates the distance between the two sets of latitudes and
        longitudes.

        Parameters
        ----------
        goog_lat : string
            Latitude for a company from google search query results
        goog_lng : float
            Longitude for a company from google search query results
        loc_lat : float
            Latitude for a user visited location
        loc_lng : float
            Longitude for a user visited location

        Attributes
        ----------
        distance : float
            Distance between the two coordinates
        """
        d_lat = goog_lat - loc_lat
        d_lng = goog_lng - loc_lng
        distance = (np.sqrt(d_lat**2+d_lng**2))

        return distance


    def data_writer(self,sql_record):
        """Helper function to write to SQL table exp_comp_type

        Query writes the results of the company type search to the
        database.

        Parameter
        ---------

        sql_record : tuple
            Contains the data to be writtne to table exp_comp_type
        """

        sql_st = '''
            INSERT OR IGNORE INTO exp_comp_type(geo_expense_id,goog_name,comp_type,address,placeid,goog_lat,goog_lng)
            VALUES (?,?,?,?,?,?,?)
        '''
        cur = self.conn.cursor()
        cur.execute(sql_st,sql_record)
        self.conn.commit()

    def exp_type_loc_table(self):
        """Aggregates SQL tables containing company type and transaction

        Insert & Join SQL statement, creating table exp_type_loc
        which contains the transaction data and predicted company name
        and company type.
        """

        sql_st = '''
            INSERT INTO exp_type_loc(yr, mnth, dy, general_name,goog_name, comp_type, country, city, state, postcode, lat,lng,goog_lat,goog_lng, value)
                SELECT yr, mnth, dy, general_name, goog_name, comp_type, country, city, state, postcode, lat,lng,goog_lat,goog_lng, value
                FROM geo_expense_data
                LEFT JOIN exp_comp_type ON geo_expense_data.id = exp_comp_type.geo_expense_id
        '''

        cur = self.conn.cursor()
        cur.execute(sql_st)
        self.conn.commit()

    def company_info_loader(self):
        """Primary aggregation launcher

        Script launches data.retriever and exp_type_loc table in order
        to retrieve the company type given a name and then aggregate,
        company type and location into a table.
        """


        self.data_retriever()
        self.exp_type_loc_table()

    def summary_table(self):
        """Creates summary transaction information to display in online table'

        Inserts summary data of expenses to be displayed online.
        """

        sql_st = '''
        INSERT OR IGNORE INTO expenses(yr, mnth, dy, general_name, comp_type,value)
        SELECT yr, mnth, dy, general_name, comp_type,value
        FROM exp_type_loc
        '''

        cur = self.conn.cursor()
        cur.execute(sql_st)
        self.conn.commit()
