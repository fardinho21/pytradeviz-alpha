import tkinter as tk


class MainWindow(tk.Tk):
    def __init__(self):
        super().__init__()

        # set up the first canvas, with large red triangle
        self.canvas1 = tk.Canvas(self, background="turquoise")
        self.canvas1.grid(column=0, row=0, sticky='news')

        self.canvas1_hscroller = tk.Scrollbar(self, orient="horizontal", command=self.canvas1.xview)
        self.canvas1_hscroller.grid(column=0, row=1, sticky='we')
        self.canvas1.configure(xscrollcommand=self.canvas1_hscroller.set)

        points = [0, 0, 1000, 800, 800, 1000]
        self.canvas1.create_polygon(points, fill="red")

        self.canvas1.configure(scrollregion=self.canvas1.bbox("all"))

        # set up the second canvas, with large green triangle
        self.canvas2 = tk.Canvas(self, background="orange")
        self.canvas2.grid(column=1, row=0, sticky='news')

        self.canvas2_hscroller = tk.Scrollbar(self, orient="horizontal", command=self.canvas2.xview)
        self.canvas2_hscroller.grid(column=1, row=1, sticky='we')
        self.canvas2.configure(xscrollcommand=self.canvas2_hscroller.set)

        points = [0, 0, 1000, 800, 800, 1000]
        self.canvas2.create_polygon(points, fill="green")

        self.canvas2.configure(scrollregion=self.canvas2.bbox("all"))

        self.v_scroller = tk.Scrollbar(self, orient='vertical', command=self.v_scroll)
        self.v_scroller.grid(column=2, row=0, sticky='ns')
        self.canvas1.config(yscrollcommand=self.v_scroller.set)

    def v_scroll(self, *args):
        self.canvas1.yview(*args)
        self.canvas2.yview(*args)


root = MainWindow()
root.mainloop()