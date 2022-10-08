import csv 
import datetime as datetime
from math import inf
class PriceDataPrepper:

    file_handle=None
    asset_pair=""
    highest_price=0
    lowest_price=inf
    price_data=[]
    date_range=()

    """
    :param <string> file_path: absolute or relative path to csv file
    :param <int> skip_lines: number of header lines to skip
    """
    def __init__(self, file_path, debug=False, skip_lines=2):

        self.read_csv_file(file_path,skip_lines)
        
        if debug:  
            print("Lowest: \n", self.lowest_price, "\nHighest: \n", self.highest_price)
        
        self.file_handle.close()

    def __repr__(self):
        
        for e in self.price_data:
            print(e)

        print("Lowest: \n", self.lowest_price, "\nHighest: \n", self.highest_price)
        return ""

    """"""
    def read_csv_file(self, file_path,  skip_lines=2):

        self.file_handle = open(file_path)
        self.csvreader = csv.reader(self.file_handle)
        
        #skip lines
        for i in range(skip_lines):
            next(self.csvreader)
        
        #read in price data
        for r in self.csvreader:
            o, h ,l ,c =float(r[3]), float(r[4]), float(r[5]), float(r[6]) 

            date_parsed= r[1].split(" ")[0].split("-")

            if h > self.highest_price:
                self.highest_price = h
            if l < self.lowest_price:
                self.lowest_price = l

            dohlc=(date_parsed, o, h, l, c)
            self.price_data.append(dohlc)

    """
    :return <dict> price_data_object: the a dictionary containing the prices, highest price, lowest price and the asset pair
    """
    def get_price_data_object(self):
        price_data_object = dict()
        price_data_object["asset_pair"] = self.asset_pair
        price_data_object["price_data"] = self.price_data
        price_data_object["highest"]= self.highest_price
        price_data_object["lowest"]= self.lowest_price
        return price_data_object