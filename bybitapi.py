import logbot
import ccxt
import time
import random
import os
import sys
from pybit import HTTP
from pprint import pprint

root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(root + '/python')

class ByBit:
    def __init__(self, var: dict):
        self.ENDPOINT = 'https://api-testnet.bybit.com'

        self.subaccount_name = var['subaccount_name']
        self.leverage = var['leverage']
        self.risk = var['risk']
        self.api_key = var['api_key']
        self.api_secret = var['api_secret']

    # =============== SIGN, POST AND REQUEST ===============
    def _try_request(self, method: str, **kwargs):
        session = HTTP(self.ENDPOINT, api_key=self.api_key, api_secret=self.api_secret)
        try:
            if method=='get_wallet_balance':
                req = session.get_wallet_balance(coin=kwargs.get('coin'))
            elif method=='my_position':
                req = session.my_position(symbol=kwargs.get('symbol'))
            elif method=='place_active_order':
                req = session.place_active_order(symbol=kwargs.get('symbol'), 
                                                    side=kwargs.get('side'), 
                                                    order_type=kwargs.get('order_type'), 
                                                    qty=kwargs.get('qty'), 
                                                    price=kwargs.get('price', None), 
                                                    stop_loss=kwargs.get('stop_loss', None), 
                                                    time_in_force=kwargs.get('time_in_force'), 
                                                    reduce_only=kwargs.get('reduce_only'), 
                                                    close_on_trigger=kwargs.get('close_on_trigger'))
            elif method=='place_conditional_order':
                req = session.place_conditional_order(symbol=kwargs.get('symbol'),
                                                        side=kwargs.get('side'),
                                                        order_type=kwargs.get('order_type'),
                                                        qty=kwargs.get('qty'),
                                                        price=kwargs.get('price'),
                                                        base_price=kwargs.get('base_price'),
                                                        stop_px=kwargs.get('stop_px'),
                                                        trigger_by=kwargs.get('trigger_by'),
                                                        time_in_force=kwargs.get('time_in_force'),
                                                        reduce_only=kwargs.get('reduce_only'),
                                                        close_on_trigger=kwargs.get('close_on_trigger'))
            elif method=='cancel_all_active_orders':
                req = session.cancel_all_active_orders(symbol=kwargs.get('symbol'))
            elif method=='cancel_all_conditional_orders':
                req = session.cancel_all_conditional_orders(symbol=kwargs.get('symbol'))
            elif method=='set_trading_stop':
                req = session.set_trading_stop(symbol=kwargs.get('symbol'), 
                                                side=kwargs.get('side'), # Side of the open position
                                                stop_loss=kwargs.get('stop_loss'))
            elif method=='query_symbol':
                req = session.query_symbol()
        except Exception as e:
            logbot.logs('>>> /!\ An exception occured : {}'.format(e), True)
            return {
                "success": False,
                "error": str(e)
            }
        if req['ret_code']:
            logbot.logs('>>> /!\ {}'.format(req['ret_msg']), True)
            return {
                    "success": False,
                    "error": req['ret_msg']
                }
        else:
            req['success'] = True
        return req

    # ================== UTILITY FUNCTIONS ==================

    def _rounded_size(self, size, qty_step):
        step_size = round(float(size) / qty_step) * qty_step
        if isinstance(qty_step, float):
            decimal = len(str(qty_step).split('.')[1])
            return round(step_size, decimal)
        return step_size
    
    # ================== ORDER FUNCTIONS ==================

    def entry_position(self, payload: dict, ticker):
        #   PLACE ORDER
        orders = []

        side = 'Buy'
        close_sl_tp_side = 'Sell'
        stop_loss = payload['long SL']
        take_profit = payload['long TP']

        if payload['action'] == 'sell':
            side = 'Sell'
            close_sl_tp_side = 'Buy'
            stop_loss = payload['short SL']
            take_profit = payload['short TP']
        
        r = self._try_request('query_symbol')
        r = r['result']
        my_item = next((item for item in r if item['name'] == 'BTCUSD'), None)
        qty_step = my_item['lot_size_filter']['qty_step']

        # 0/ Get free collateral and calculate position
        r = self._try_request('get_wallet_balance', coin="BTC")
        if not r['success']:
            return r
        free_collateral = r['result']['BTC']['available_balance']
        logbot.logs('>>> Found free collateral : {}'.format(free_collateral))
        
        #FIXED TO A FIXED NUMBER OF SIZE - 100% ? Next maybe do size depending on the signal sent.
        size = (free_collateral*payload['price'])*0.95

        logbot.logs(f">>> SIZE : {size}")
            
        size = self._rounded_size(size, qty_step)

        logbot.logs(f">>> SIZE : {size}, SIDE : {side}, PRICE : {payload['price']}, SL : {stop_loss}, TP : {take_profit}")

        logbot.logs(r['result'])
     
        # 1/ place order with stop loss
        if 'type' in payload.keys():
            order_type = payload['type'] # 'market' or 'limit'
            order_type = order_type.capitalize()
        else:
            order_type = 'Market' # per defaut market if none is specified
        if order_type != 'Market' and order_type != 'Limit':
            return {
                    "success" : False,
                    "error" : f"order type '{order_type}' is unknown"
                }

        if order_type == "Market" : 
            exe_price = None if order_type == "Market" else payload['price']
            r = self._try_request('place_active_order', 
                                symbol=ticker, 
                                side=side, 
                                order_type=order_type, 
                                qty=size, 
                                price=exe_price, 
                                stop_loss=stop_loss, 
                                time_in_force="GoodTillCancel", 
                                reduce_only=False, 
                                close_on_trigger=False)
        else : 
            exe_price=payload['price']

            print('CCXT Version:', ccxt.__version__)

            exchange = ccxt.bybit ({
                'apiKey': self.api_key,
                'secret': self.api_secret,
                'enableRateLimit': True,  # https://github.com/ccxt/ccxt/wiki/Manual#rate-limit
            })
            exchange.set_sandbox_mode(True)

            markets = exchange.load_markets()

            symbol = 'BTC/USD'
            market = exchange.market(symbol)

            response = exchange.v2_private_get_position_list({'symbol':market['id']})
            inverse_positions = response['result']

            logbot.logs(inverse_positions)

            test = self._try_request('my_position', symbol=ticker)

            logbot.logs("TEST POSITION DATA")
            logbot.logs(test)
            
            logbot.logs("What about here?")
            since = exchange.milliseconds () - 86400000  # -1 day from now
            #logbot.logs(exchange.fetch_orders(symbol,since,20))

            def refresh_order(order):
                since = exchange.milliseconds () - 86400000  # -1 day from now
                updated_orders = exchange.fetch_orders(symbol,since,20)
                for updated_order in updated_orders:
                    if updated_order["id"] == order["id"]:
    
                        return updated_order
                logbot.logs("!!!!>>> PRINT ORDER 11<<<!!!!")
                logbot.logs(order["id"])
                logbot.logs("Failed to find order {}".format(order["id"]))
                return None

            ticker = "BTCUSD"

            min_size = 1

            #Is the amount=size correct? if it doesnt work try something else...
            amount = size
            amount_traded = 0

            order = None
            bid, ask = 0, 1e10

            while amount - amount_traded > min_size:
                move = False
                ticker_data = exchange.fetch_ticker(ticker)
                new_bid, new_ask = ticker_data['bid'], ticker_data['ask']

                if bid != new_bid:
                    bid = new_bid

                    # If an order ccxt_bybitists then cancel it
                    if order is not None:
                         # cancel order
                        try:
                            exchange.cancel_order(order["id"])
                        except Exception as e:
                            print(e)

                        # refresh order details and track how much we got filled
                        order = refresh_order(order)
                        amount_traded += float(order["info"]["filledSize"])

                        #exit now if we're done!
                        if amount - amount_traded < min_size:
                            break

                    # place order
                    order = exchange.create_limit_buy_order(ticker, amount, new_bid, {"postOnly": True})
                    logbot.logs("NEW ORDER CREATED!!!")
                    logbot.logs(order)

                    print("Buy {} {} at {}".format(amount, ticker, new_bid))
                    time.sleep(random.random())

                # Even if the price has not moved, check how much we have filled.
                if order is not None:
                    order = refresh_order(order)
                    
                    logbot.logs("TEST KEJ NAM VRNE ORDER TLE!!!!")
                    logbot.logs(order)

                    amount_traded += float(order["info"]["filledSize"])
                time.sleep(0.1)

                logbot.logs(">>>Finished buying {} of {}".format(amount, ticker))
            
        if not r['success']:
            r['orders'] = orders
            return r
        orders.append(r['result'])
        logbot.logs(f">>> Order {order_type} posted with success")

        # 2/ place the take profit only if it is not None or 0
        if take_profit:
            if order_type == 'Market':
                r = self._try_request('place_active_order', 
                                    symbol=ticker, 
                                    side=close_sl_tp_side, 
                                    order_type="Limit", # so we avoid paying fees on market take profit
                                    qty=size, 
                                    price=take_profit,
                                    time_in_force="GoodTillCancel", 
                                    reduce_only=True, 
                                    close_on_trigger=False)
                if not r['success']:
                    r['orders'] = orders
                    return r
                orders.append(r['result'])
                logbot.logs(">>> Take profit posted with success")
            else: # Limit order type
                
                r = self._try_request('place_conditional_order', 
                                    symbol=ticker, 
                                    side=close_sl_tp_side, 
                                    order_type="Limit", 
                                    qty=size, 
                                    price=take_profit, 
                                    base_price=exe_price, 
                                    stop_px=exe_price, 
                                    trigger_by='LastPrice', 
                                    time_in_force="GoodTillCancel", 
                                    reduce_only=False, # Do not set to True
                                    close_on_trigger=False)
                if not r['success']:
                    r['orders'] = orders
                    return r
                orders.append(r['result'])
                logbot.logs(">>> Take profit posted with success")
                

        # 3/ (optional) place multiples take profits
        i = 1
        while True:
            tp = 'tp' + str(i) + ' Mult'
            if tp in payload.keys():
                # place limit order
                dist = abs(payload['price'] - stop_loss) * payload[tp]
                mid_take_profit = (payload['price'] + dist) if  side == 'Buy' else (payload['price'] - dist)
                mid_size = size * (payload['tp Close'] / 100)
                mid_size = self._rounded_size(mid_size, qty_step)
                if order_type == 'Market':
                    r = self._try_request('place_active_order', 
                            symbol=ticker, 
                            side=close_sl_tp_side, 
                            order_type="Limit", # so we avoid paying fees on market take profit
                            qty=mid_size, 
                            price=mid_take_profit,
                            time_in_force="GoodTillCancel", 
                            reduce_only=True, 
                            close_on_trigger=False)
                    if not r['success']:
                        r['orders'] = orders
                        return r
                    orders.append(r['result'])
                    logbot.logs(f">>> Take profit {i} posted with success at price {mid_take_profit} with size {mid_size}")
                else: # Stop limit type
                    r = self._try_request('place_conditional_order', 
                                    symbol=ticker, 
                                    side=close_sl_tp_side, 
                                    order_type="Limit", 
                                    qty=mid_size, 
                                    price=mid_take_profit, 
                                    base_price=exe_price, 
                                    stop_px=exe_price, 
                                    trigger_by='LastPrice', 
                                    time_in_force="GoodTillCancel", 
                                    reduce_only=False, # Do not set to True
                                    close_on_trigger=False)
                    if not r['success']:
                        r['orders'] = orders
                        return r
                    orders.append(r['result'])
                    logbot.logs(f">>> Take profit {i} posted with success at price {mid_take_profit} with size {mid_size}")
            else:
                break
            i += 1
        
        return {
            "success": True,
            "orders": orders
        }
        
    def exit_position(self, ticker):
        #   CLOSE POSITION IF ONE IS ONGOING
        r = self._try_request('my_position', symbol=ticker)
        if not r['success']:
            return r
        logbot.logs(">>> Retrieve positions")

        for position in r['result']:
            open_size = r['result'].get('size')
            if open_size > 0:
                open_side = r['result'].get('side')
                close_side = 'Sell' if open_side == 'Buy' else 'Buy'
                
                r = self._try_request('place_active_order', 
                                    symbol=ticker,
                                    side=close_side,
                                    order_type="Market",
                                    qty=open_size,
                                    price=None,
                                    time_in_force="GoodTillCancel",
                                    reduce_only=True,
                                    close_on_trigger=False)

                if not r['success']:
                    return r
                logbot.logs(">>> Close ongoing position with success")

                break

        #   DELETE ALL OPEN AND CONDITIONAL ORDERS REMAINING
        r = self._try_request('cancel_all_active_orders', symbol=ticker)
        if not r['success']:
            return r
        r = self._try_request('cancel_all_conditional_orders', symbol=ticker)
        if not r['success']:
            return r
        logbot.logs(">>> Deleted all open and conditional orders remaining with success")
        
        return {
            "success": True
        }

    def breakeven(self, payload: dict, ticker):
        #   SET STOP LOSS TO BREAKEVEN
        r = self._try_request('my_position', symbol=ticker)
        if not r['success']:
            return r
        logbot.logs(">>> Retrieve positions")

        orders = []

        for position in r['result']:
            open_size = r['result'].get('size')
            if open_size > 0:
                open_side = r['result'].get('side')
                # close_side = 'Sell' if open_side == 'Buy' else 'Buy'
                logbot.logs("payload")
                breakeven_price = payload['long Breakeven'] if open_side == 'Buy' else payload['short Breakeven']

                # place market stop loss at breakeven
                r = self._try_request('set_trading_stop', 
                                    symbol=ticker, 
                                    side=open_side, # Side of the open position
                                    stop_loss=breakeven_price)
                if not r['success']:
                    return r
                orders.append(r['result'])
                logbot.logs(f">>> Breakeven stop loss posted with success at price {breakeven_price}")

        return {
            "success": True,
            "orders": orders
        }
#TEST