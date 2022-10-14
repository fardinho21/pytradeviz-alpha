
class Indicators:

    price_data=None


    def __init__(self, tk_canvas=None, price_data=None):
        self.price_data=price_data
        pass

    def set_price_data(self, price_data):
        self.price_data=price_data

    def render_RSI(self, tk_indicators_canvas, divider_v):
        first = True
        previous = []
        
        for i in range(len(self.price_data)):
            row = self.price_data[i]
            pos = divider_v*i
            
            if len(row) == 6:
                rsi = row[5]

                if first:
                    tk_indicators_canvas.create_line(0, 100, pos, 100 - rsi, fill="black")
                    first = False

                else: 
                    tk_indicators_canvas.create_line(previous[0], 100 - previous[1], pos, 100 - rsi, fill="black")

                previous = [pos, rsi]
        pass

    def render_SMA(self):
        pass

    def render_EMA(self):
        pass

    def calculate_RSI(self, avg_gain, avg_loss):
        return 100 - (100/ (1 + (avg_gain/avg_loss)))

    def calculate_RSI_full(self, period=7):
        
        avg_gain_updated = False
        avg_loss_updated = False

        #step one 
        gainloss = self.RSI_step_one(period)
        
        prev_avg_gain = gainloss[0]
        prev_avg_loss = gainloss[1]

        running_avg_loss = 0
        running_avg_gain = 0

        window_s = period

        #step two
        for i in range(window_s, len(self.price_data)):
            rsi = 0

            data_row = self.price_data[i]
            open = data_row[1]
            close = data_row[4]

            if open < close:
                avg_gain_updated = True
                running_avg_gain = close - open
                running_avg_gain = (prev_avg_gain * (period - 1) + (running_avg_gain))/period
                prev_avg_gain = running_avg_gain

            elif open > close:
                avg_loss_updated = True
                running_avg_loss = open - close
                running_avg_loss = (prev_avg_loss * (period - 1) + (running_avg_loss))/period
                prev_avg_loss = running_avg_loss

            if avg_gain_updated and avg_loss_updated:
                avg_gain_updated = False
                avg_loss_updated = False

                rsi = self.calculate_RSI(running_avg_gain, running_avg_loss)
                self.price_data[i].append(rsi)

        for e in self.price_data:
            print(e)

    def RSI_step_one(self, period):

        avg_gain_one = 0
        avg_loss_one = 0

        #find avg gain and loss
        for i in range(period):
            
            data_row = self.price_data[i]
            open = data_row[1]
            close = data_row[4]

            if open < close:
                avg_gain_one += close - open
            elif open > close:
                avg_loss_one += open - close

        avg_gain_one = avg_gain_one/period
        avg_loss_one = avg_loss_one/period

        rsi = self.calculate_RSI(avg_gain_one, avg_loss_one)

        self.price_data[period - 1].append(rsi)

        return [avg_gain_one, avg_loss_one, rsi]

    def calculate_SMA(self, period=7):
        pass

    def calculate_EMA(self, period=7):
        pass