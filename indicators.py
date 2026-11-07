
class Indicators:

    price_data=None


    def __init__(self, tk_canvas=None, price_data=None):
        self.price_data=price_data
        self._rsi_state = None
        pass

    def set_price_data(self, price_data):
        self.price_data=price_data
        self._rsi_state = None

    def render_RSI(self, tk_indicators_canvas, divider_v, offset_x=0,
                   start=0, tags=()):
        previous = None
        for i in range(start - 1, -1, -1):
            if self.price_data[i][5]["rsi"]:
                previous = (offset_x + divider_v * i, self.price_data[i][5]["rsi"])
                break
        
        for i in range(start, len(self.price_data)):
            row = self.price_data[i]
            pos = offset_x + divider_v*i
            
            if row[5]["rsi"]:
                rsi = row[5]["rsi"]

                if previous is None:
                    tk_indicators_canvas.create_line(offset_x, 100, pos, 100 - rsi, fill="black", tags=tags)
                else:
                    tk_indicators_canvas.create_line(previous[0], 100 - previous[1], pos, 100 - rsi, fill="black", tags=tags)

                previous = [pos, rsi]
        pass

    def render_SMA(self):
        pass

    def render_EMA(self):
        pass

    def calculate_RSI(self, avg_gain, avg_loss):
        if avg_loss == 0:
            return 100 if avg_gain > 0 else 0
        return 100 - (100/ (1 + (avg_gain/avg_loss)))

    def calculate_RSI_full(self, period=7):
        self._rsi_state = None
        self.calculate_RSI_incremental(period)

    def calculate_RSI_incremental(self, period=7):
        if len(self.price_data) < period:
            return
        if self._rsi_state is None:
            gainloss = self.RSI_step_one(period)
            self._rsi_state = {
                "period": period, "next_index": period,
                "prev_gain": gainloss[0], "prev_loss": gainloss[1],
                "running_gain": 0, "running_loss": 0,
                "gain_updated": False, "loss_updated": False,
            }
        state = self._rsi_state
        if state["period"] != period:
            raise ValueError("RSI period cannot change during incremental calculation")

        for i in range(state["next_index"], len(self.price_data)):
            rsi = 0

            data_row = self.price_data[i]
            open = data_row[1]
            close = data_row[4]

            if open < close:
                state["gain_updated"] = True
                state["running_gain"] = (state["prev_gain"] * (period - 1) + close - open) / period
                state["prev_gain"] = state["running_gain"]

            elif open > close:
                state["loss_updated"] = True
                state["running_loss"] = (state["prev_loss"] * (period - 1) + open - close) / period
                state["prev_loss"] = state["running_loss"]

            if state["gain_updated"] and state["loss_updated"]:
                state["gain_updated"] = False
                state["loss_updated"] = False

                rsi = self.calculate_RSI(state["running_gain"], state["running_loss"])
                self.price_data[i][5]["rsi"] = rsi
        state["next_index"] = len(self.price_data)

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

        self.price_data[period - 1][5]["rsi"] = rsi

        return [avg_gain_one, avg_loss_one, rsi]

    def calculate_SMA(self, period=7):
        pass

    def calculate_EMA(self, period=7):
        pass