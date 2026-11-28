""" This basic example demonstrates how to list all tabs.
"""
import dataclasses
import asyncio
from tkinter import messagebox
from typing import Any, List
from django.test import client
from geckordp.actors.events import Events
from geckordp.actors.root import RootActor
from geckordp.actors.web_console import WebConsoleActor
from geckordp.firefox import Firefox
from geckordp.profile import ProfileManager
from geckordp.rdp_client import RDPClient
from geckordp.actors.descriptors.tab import TabActor


class PriceUpdater():
    
    def __init__(self):
        pass

    _js = """
    (() => {
        var output=''
        var table_body=document.getElementsByTagName('tbody')
        for (var e of table_body){
            var table_row = e.getElementsByTagName('tr')
            for (var ee of table_row){
                var table_data = Array.from(ee.getElementsByTagName('td'))
                var data_ohlcv=table_data.slice(0,5)
                data_ohlcv.push(table_data[6])
                var date_ohlc=''
                for (var eee of table_data){
                    date_ohlc+=eee.innerText.replaceAll(',','')+','
                }
                output+=date_ohlc+'\\n'
            }
        }
        return output;
    })()
    """
    _profile_manager = ProfileManager()
    _profile_manager.clone("default-release", "geckordp")
    _profile = _profile_manager.get_profile_by_name("geckordp")
    _profile.set_required_configs()
    _base_url="https://finance.yahoo.com/quote/TICKER/history"
    _loop=None
    _result_future=None
    response:dict={}
    def _on_evaluation_result(self, data:dict):
        if not self._result_future.done():
            self._loop.call_soon_threadsafe(self._result_future.set_result, data)
        pass
    async def _update_price(self, ticker_symbol:str, window: Any) -> None | List[str]:
        if not ticker_symbol:
            messagebox.showerror("No ticker is loaded.", parent=window)
            return 
        
        Firefox.start(self._base_url.replace("TICKER",ticker_symbol), "42069", "geckordp", ["-headless"])
        
        client = RDPClient()
        client.connect("localhost", "42069")
        root = RootActor(client)
        tab_ctx = root.list_tabs()[0]
        tab_actor = TabActor(client, tab_ctx["actor"])
        actor_ids = tab_actor.get_target()
        console_actor_id = actor_ids["consoleActor"]
        console=WebConsoleActor(client, console_actor_id)
        console.start_listeners([])
        self._loop = asyncio.get_running_loop()
        self._result_future = self._loop.create_future()
        client.add_event_listener(console_actor_id, Events.WebConsole.EVALUATION_RESULT, self._on_evaluation_result)
        console.evaluate_js_async(self._js)
        self.response = await self._result_future
        
        client.remove_event_listener(
        console_actor_id, 
        Events.WebConsole.EVALUATION_RESULT, 
        self._on_evaluation_result
    )
        client.disconnect()
    def run(self, t:str, w:Any=None):
        asyncio.run(self._update_price(t,w))
    


PU= PriceUpdater()
PU.run("NVDA", None)


print(PU.response["result"]["initial"])