import csv 
from math import inf

class PriceDataPrepper:

    file_handle=None
    asset_pair=""
    highest_price=0
    lowest_price=inf
    price_data=[]

    """
    :param <string> file_path: absolute or relative path to csv file
    :param <int> skip_lines: number of header lines to skip
    """
    def __init__(self, file_path, skip_lines=2, asset_pair="XRP/USDT"):
        self.asset_pair=asset_pair
        self.file_handle = open(file_path)
        self.csvreader = csv.reader(self.file_handle)

        #skip lines / header
        for i in range(skip_lines):
            next(self.csvreader)

        for r in self.csvreader:
            dohlc=(r[1],float(r[3]),float(r[4]),float(r[5]),float(r[6]))
            self.price_data.append(dohlc)
        
        for dohlc in self.price_data:
            if dohlc[2] > self.highest_price:
                self.highest_price = dohlc[2]
            if dohlc[3] < self.lowest_price:
                self.lowest_price = dohlc[3]
    
    """
    :return <str>: the highest, the lowest, and the asset pair
    """  
    def __repr__(self):
        return "Lowest: \n" + \
            str(self.lowest_price) + \
            "\nHighest: \n" + \
            str(self.highest_price) + \
            "\nAsset: \n" + self.asset_pair + "\n"

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