
class Candle:
    
    
    
    def __init__(self, open, high, low, close):
        self.open=open
        self.high=high
        self.low=low
        self.close=close
        self.color="grey"
        self.body="solid"

        if open < close:
            self.color="red"
            self.body="hollow"
        
    def get_body(self):
        return self.body
    def set_body(self, body):
        self.body=body

    def get_color(self):
        return self.color
    def set_color(self, color):
        self.color=color

    def get_ohlc(self):
        return [self.open, self.high, self.low,  self.close]    
    def set_ohlc(self, ohlc_ary):
        self.open=ohlc_ary[0]
        self.high=ohlc_ary[1]
        self.low=ohlc_ary[2]
        self.close=ohlc_ary[3]

    """
    Draw the candle on a tkinter canvas
    """
    def draw_candle(self, tk_canvas):
        pass