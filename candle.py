
class Candle:
    candle_width=5
    cents_per_pixle=0

    def __init__(self, open, high, low, close, date, cppx=0):
        self.open=open
        self.high=high
        self.low=low
        self.close=close
        self.color="grey"
        self.body="hollow"
        self.date=date
        self.cents_per_pixle=cppx

        self.render_open=(open*100)/cppx
        self.render_high=(high*100)/cppx
        self.render_low=(low*100)/cppx
        self.render_close=(close*100)/cppx

        if open < close:
            self.color="green"
            self.body="solid"
        elif close < open:
            self.color="red"

        
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
        self.draw_high_low(tk_canvas)
        self.draw_open_close(tk_canvas, True)
        pass

    """
    Draw the high and low as a line
    """
    def draw_high_low(self, tk_canvas):
        tk_canvas.create_line(self.date, self.render_high, self.date, self.render_low, fill=self.color, width=3)
        pass

    """
    Draw open and close as a line 
    """
    def draw_open_close(self, tk_canvas, candle=False):
        if candle:
            fill= "" if (self.body == "hollow") else "green"
                
            tk_canvas.create_rectangle(self.date - self.candle_width, self.open, self.date + self.candle_width, self.close, fill=fill)
        else:
            tk_canvas.create_line(self.date, self.open, self.date, self.close, fill=self.color, width=3)

        pass