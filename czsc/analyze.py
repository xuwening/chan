# coding: utf-8

import warnings
try:
    import talib as ta
except ImportError:
    from czsc import ta
    ta_lib_hint = "没有安装 ta-lib !!! 请到 https://www.lfd.uci.edu/~gohlke/pythonlibs/#ta-lib " \
                  "下载对应版本安装，预计分析速度提升2倍"
    warnings.warn(ta_lib_hint)
import pandas as pd
import numpy as np
from datetime import datetime
from czsc.utils import plot_ka, plot_kline


def find_zs(points):
    """输入笔或线段标记点，输出中枢识别结果"""
    if len(points) <= 4:
        return []

    # 当输入为笔的标记点时，新增 xd 值
    for i, x in enumerate(points):
        if x.get("bi", 0):
            points[i]['xd'] = x["bi"]

    k_xd = points
    k_zs = []
    zs_xd = []

    for i in range(len(k_xd)):
        if len(zs_xd) < 5:
            zs_xd.append(k_xd[i])
            continue
        xd_p = k_xd[i]
        zs_d = max([x['xd'] for x in zs_xd[:4] if x['fx_mark'] == 'd'])
        zs_g = min([x['xd'] for x in zs_xd[:4] if x['fx_mark'] == 'g'])
        if zs_g <= zs_d:
            zs_xd.append(k_xd[i])
            zs_xd.pop(0)
            continue

        # 定义四个指标,GG=max(gn),G=min(gn),D=max(dn),DD=min(dn)，n遍历中枢中所有Zn。
        # 特别地，再定义ZG=min(g1、g2), ZD=max(d1、d2)，显然，[ZD，ZG]就是缠中说禅走势中枢的区间
        if xd_p['fx_mark'] == "d" and xd_p['xd'] > zs_g:
            # 线段在中枢上方结束，形成三买
            k_zs.append({
                'ZD': zs_d,
                "ZG": zs_g,
                'G': min([x['xd'] for x in zs_xd if x['fx_mark'] == 'g']),
                'GG': max([x['xd'] for x in zs_xd if x['fx_mark'] == 'g']),
                'D': max([x['xd'] for x in zs_xd if x['fx_mark'] == 'd']),
                'DD': min([x['xd'] for x in zs_xd if x['fx_mark'] == 'd']),
                "points": zs_xd,
                "third_buy": xd_p
            })
            zs_xd = k_xd[i - 1: i + 1]
        elif xd_p['fx_mark'] == "g" and xd_p['xd'] < zs_d:
            # 线段在中枢下方结束，形成三卖
            k_zs.append({
                'ZD': zs_d,
                "ZG": zs_g,
                'G': min([x['xd'] for x in zs_xd if x['fx_mark'] == 'g']),
                'GG': max([x['xd'] for x in zs_xd if x['fx_mark'] == 'g']),
                'D': max([x['xd'] for x in zs_xd if x['fx_mark'] == 'd']),
                'DD': min([x['xd'] for x in zs_xd if x['fx_mark'] == 'd']),
                "points": zs_xd,
                "third_sell": xd_p
            })
            zs_xd = k_xd[i - 1: i + 1]
        else:
            zs_xd.append(xd_p)

    if len(zs_xd) >= 5:
        zs_d = max([x['xd'] for x in zs_xd[:4] if x['fx_mark'] == 'd'])
        zs_g = min([x['xd'] for x in zs_xd[:4] if x['fx_mark'] == 'g'])
        k_zs.append({
            'ZD': zs_d,
            "ZG": zs_g,
            'G': min([x['xd'] for x in zs_xd if x['fx_mark'] == 'g']),
            'GG': max([x['xd'] for x in zs_xd if x['fx_mark'] == 'g']),
            'D': max([x['xd'] for x in zs_xd if x['fx_mark'] == 'd']),
            'DD': min([x['xd'] for x in zs_xd if x['fx_mark'] == 'd']),
            "points": zs_xd,
        })

    return k_zs


class Section:
    """走势截面"""
    def __init__(self, kline_new, fx_list, bi_list, xd_list):
        self.kline_new = kline_new
        self.fx_list = fx_list
        self.bi_list = bi_list
        self.xd_list = xd_list


class KlineAnalyze:
    def __init__(self, kline, name="本级别", min_bi_k=5, bi_mode="old",
                 max_raw_len=10000, ma_params=(5, 20, 120), verbose=False):
        """

        :param kline: list or pd.DataFrame
        :param name: str
        :param min_bi_k: int
            笔内部的最少K线数量
        :param bi_mode: str
            new 新笔；old 老笔；默认值为 old
        :param max_raw_len: int
            原始K线序列的最大长度
        :param ma_params: tuple of int
            均线系统参数
        :param verbose: bool
        """
        self.name = name
        self.verbose = verbose
        self.min_bi_k = min_bi_k
        self.bi_mode = bi_mode
        self.max_raw_len = max_raw_len
        self.ma_params = ma_params
        self.kline_raw = []     # 原始K线序列
        self.kline_new = []     # 去除包含关系的K线序列

        # 辅助技术指标
        self.ma = []
        self.macd = []

        # 分型、笔、线段
        self.fx_list = []
        self.bi_list = []
        self.xd_list = []

        # # 中枢识别结果
        # self.zs_list_l1 = []
        # self.zs_list_l2 = []
        # self.zs_list_l3 = []
        #
        # # 走势分段结果
        # self.fd_list_l1 = []
        # self.fd_list_l2 = []
        # self.fd_list_l3 = []

        # 根据输入K线初始化
        if isinstance(kline, pd.DataFrame):
            columns = kline.columns.to_list()
            self.kline_raw = [{k: v for k, v in zip(columns, row)} for row in kline.values]
        else:
            self.kline_raw = kline

        self.kline_raw = self.kline_raw[-self.max_raw_len:]
        self.symbol = self.kline_raw[0]['symbol']
        self.start_dt = self.kline_raw[0]['dt']
        self.end_dt = self.kline_raw[-1]['dt']
        self.latest_price = self.kline_raw[-1]['close']

        self._update_ta()
        self._update_kline_new()
        self._update_fx_list()
        self._update_bi_list()
        self._update_xd_list()

    def _update_ta(self):
        """更新辅助技术指标"""
        if not self.ma:
            ma_temp = dict()
            close_ = np.array([x["close"] for x in self.kline_raw], dtype=np.double)
            for p in self.ma_params:
                ma_temp['ma%i' % p] = ta.SMA(close_, p)

            for i in range(len(self.kline_raw)):
                ma_ = {'ma%i' % p: ma_temp['ma%i' % p][i] for p in self.ma_params}
                ma_.update({"dt": self.kline_raw[i]['dt']})
                self.ma.append(ma_)
        else:
            ma_ = {'ma%i' % p: sum([x['close'] for x in self.kline_raw[-p:]]) / p
                   for p in self.ma_params}
            ma_.update({"dt": self.kline_raw[-1]['dt']})
            if self.verbose:
                print("ma new: %s" % str(ma_))

            if self.kline_raw[-2]['dt'] == self.ma[-1]['dt']:
                self.ma.append(ma_)
            else:
                self.ma[-1] = ma_

        assert self.ma[-2]['dt'] == self.kline_raw[-2]['dt']

        if not self.macd:
            close_ = np.array([x["close"] for x in self.kline_raw], dtype=np.double)
            # m1 is diff; m2 is dea; m3 is macd
            m1, m2, m3 = ta.MACD(close_, fastperiod=12, slowperiod=26, signalperiod=9)
            for i in range(len(self.kline_raw)):
                self.macd.append({
                    "dt": self.kline_raw[i]['dt'],
                    "diff": m1[i],
                    "dea": m2[i],
                    "macd": m3[i]
                })
        else:
            close_ = np.array([x["close"] for x in self.kline_raw[-200:]], dtype=np.double)
            # m1 is diff; m2 is dea; m3 is macd
            m1, m2, m3 = ta.MACD(close_, fastperiod=12, slowperiod=26, signalperiod=9)
            macd_ = {
                    "dt": self.kline_raw[-1]['dt'],
                    "diff": m1[-1],
                    "dea": m2[-1],
                    "macd": m3[-1]
                }
            if self.verbose:
                print("macd new: %s" % str(macd_))

            if self.kline_raw[-2]['dt'] == self.macd[-1]['dt']:
                self.macd.append(macd_)
            else:
                self.macd[-1] = macd_

        assert self.macd[-2]['dt'] == self.kline_raw[-2]['dt']

    def _update_kline_new(self):
        """更新去除包含关系的K线序列"""
        if len(self.kline_new) == 0:
            for x in self.kline_raw[:4]:
                self.kline_new.append(dict(x))

        # 新K线只会对最后一个去除包含关系K线的结果产生影响
        self.kline_new = self.kline_new[:-2]
        if len(self.kline_new) <= 4:
            right_k = [x for x in self.kline_raw if x['dt'] > self.kline_new[-1]['dt']]
        else:
            right_k = [x for x in self.kline_raw[-100:] if x['dt'] > self.kline_new[-1]['dt']]

        if len(right_k) == 0:
            return

        for k in right_k:
            k = dict(k)
            last_kn = self.kline_new[-1]
            if self.kline_new[-1]['high'] > self.kline_new[-2]['high']:
                direction = "up"
            else:
                direction = "down"

            # 判断是否存在包含关系
            cur_h, cur_l = k['high'], k['low']
            last_h, last_l = last_kn['high'], last_kn['low']
            if (cur_h <= last_h and cur_l >= last_l) or (cur_h >= last_h and cur_l <= last_l):
                self.kline_new.pop(-1)
                # 有包含关系，按方向分别处理
                if direction == "up":
                    last_h = max(last_h, cur_h)
                    last_l = max(last_l, cur_l)
                elif direction == "down":
                    last_h = min(last_h, cur_h)
                    last_l = min(last_l, cur_l)
                else:
                    raise ValueError

                k.update({"high": last_h, "low": last_l})
                # 保留红绿不变
                if k['open'] >= k['close']:
                    k.update({"open": last_h, "close": last_l})
                else:
                    k.update({"open": last_l, "close": last_h})
            self.kline_new.append(k)

    def _update_fx_list(self):
        """更新分型序列"""
        if len(self.kline_new) < 3:
            return

        self.fx_list = self.fx_list[:-1]
        if len(self.fx_list) == 0:
            kn = self.kline_new
        else:
            kn = [x for x in self.kline_new[-100:] if x['dt'] >= self.fx_list[-1]['dt']]

        i = 1
        while i <= len(kn)-2:
            k1, k2, k3 = kn[i-1: i+2]

            if k1['high'] < k2['high'] > k3['high']:
                if self.verbose:
                    print("顶分型：{} - {} - {}".format(k1['dt'], k2['dt'], k3['dt']))
                fx = {
                    "dt": k2['dt'],
                    "fx_mark": "g",
                    "fx": k2['high'],
                    "fx_high": k2['high'],
                    "fx_low": max(k1['low'], k3['low']),
                }
                self.fx_list.append(fx)

            elif k1['low'] > k2['low'] < k3['low']:
                if self.verbose:
                    print("底分型：{} - {} - {}".format(k1['dt'], k2['dt'], k3['dt']))
                fx = {
                    "dt": k2['dt'],
                    "fx_mark": "d",
                    "fx": k2['low'],
                    "fx_high": min(k1['high'], k2['high']),
                    "fx_low": k2['low'],
                }
                self.fx_list.append(fx)

            else:
                if self.verbose:
                    print("无分型：{} - {} - {}".format(k1['dt'], k2['dt'], k3['dt']))
            i += 1

    def _update_bi_list(self):
        """更新笔序列

        笔标记样例：
         {'dt': Timestamp('2020-05-25 15:00:00'),
          'fx_mark': 'd',
          'fx_high': 2821.5,
          'fx_low': 2802.47,
          'bi': 2802.47}

         {'dt': Timestamp('2020-07-09 15:00:00'),
          'fx_mark': 'g',
          'fx_high': 3456.97,
          'fx_low': 3366.08,
          'bi': 3456.97}

        """
        if len(self.fx_list) < 2:
            return

        self.bi_list = self.bi_list[:-1]
        if len(self.bi_list) == 0:
            for fx in self.fx_list[:2]:
                bi = dict(fx)
                bi['bi'] = bi.pop('fx')
                self.bi_list.append(bi)

        if len(self.bi_list) <= 2:
            right_fx = [x for x in self.fx_list if x['dt'] > self.bi_list[-1]['dt']]
            if self.bi_mode == "old":
                right_kn = [x for x in self.kline_new if x['dt'] >= self.bi_list[-1]['dt']]
            elif self.bi_mode == 'new':
                right_kn = [x for x in self.kline_raw if x['dt'] >= self.bi_list[-1]['dt']]
            else:
                raise ValueError
        else:
            right_fx = [x for x in self.fx_list[-50:] if x['dt'] > self.bi_list[-1]['dt']]
            if self.bi_mode == "old":
                right_kn = [x for x in self.kline_new[-300:] if x['dt'] >= self.bi_list[-1]['dt']]
            elif self.bi_mode == 'new':
                right_kn = [x for x in self.kline_raw[-300:] if x['dt'] >= self.bi_list[-1]['dt']]
            else:
                raise ValueError

        for fx in right_fx:
            last_bi = self.bi_list[-1]
            bi = dict(fx)
            bi['bi'] = bi.pop('fx')
            if last_bi['fx_mark'] == fx['fx_mark']:
                if (last_bi['fx_mark'] == 'g' and last_bi['bi'] < bi['bi']) \
                        or (last_bi['fx_mark'] == 'd' and last_bi['bi'] > bi['bi']):
                    if self.verbose:
                        print("笔标记移动：from {} to {}".format(self.bi_list[-1], bi))
                    self.bi_list[-1] = bi
            else:
                kn_inside = [x for x in right_kn if last_bi['dt'] <= x['dt'] <= bi['dt']]
                if len(kn_inside) >= self.min_bi_k:
                    # 确保相邻两个顶底之间不存在包含关系
                    if (last_bi['fx_mark'] == 'g' and bi['fx_high'] < last_bi['fx_low']) or \
                            (last_bi['fx_mark'] == 'd' and bi['fx_low'] > last_bi['fx_high']):
                        if self.verbose:
                            print("新增笔标记：{}".format(bi))
                        self.bi_list.append(bi)

        if (self.bi_list[-1]['fx_mark'] == 'd' and self.kline_new[-1]['low'] < self.bi_list[-1]['bi']) \
                or (self.bi_list[-1]['fx_mark'] == 'g' and self.kline_new[-1]['high'] > self.bi_list[-1]['bi']):
            if self.verbose:
                print("最后一个笔标记无效，{}".format(self.bi_list[-1]))
            self.bi_list.pop(-1)

    @staticmethod
    def _make_standard_seq(bi_seq):
        """计算标准特征序列

        :return: list of dict
        """
        if bi_seq[0]['fx_mark'] == 'd':
            direction = "up"
        elif bi_seq[0]['fx_mark'] == 'g':
            direction = "down"
        else:
            raise ValueError

        raw_seq = [{"dt": bi_seq[i].dt,
                    'high': max(bi_seq[i].price, bi_seq[i + 1].price),
                    'low': min(bi_seq[i].price, bi_seq[i + 1].price)}
                   for i in range(1, len(bi_seq), 2) if i <= len(bi_seq) - 2]

        seq = []
        for row in raw_seq:
            if not seq:
                seq.append(row)
                continue
            last = seq[-1]
            cur_h, cur_l = row['high'], row['low']
            last_h, last_l = last['high'], last['low']

            # 左包含 or 右包含
            if (cur_h <= last_h and cur_l >= last_l) or (cur_h >= last_h and cur_l <= last_l):
                seq.pop(-1)
                # 有包含关系，按方向分别处理
                if direction == "up":
                    last_h = max(last_h, cur_h)
                    last_l = max(last_l, cur_l)
                elif direction == "down":
                    last_h = min(last_h, cur_h)
                    last_l = min(last_l, cur_l)
                else:
                    raise ValueError
                seq.append({"dt": row['dt'], "high": last_h, "low": last_l})
            else:
                seq.append(row)
        return seq

    def _update_xd_list(self):
        """更新线段序列"""
        if len(self.bi_list) < 4:
            return

        self.xd_list = self.xd_list[:-2]
        if len(self.xd_list) == 0:
            for i in range(3):
                xd = dict(self.bi_list[i])
                xd['xd'] = xd.pop('bi')
                self.xd_list.append(xd)

        if len(self.xd_list) <= 3:
            right_bi = [x for x in self.bi_list if x['dt'] >= self.xd_list[-1]['dt']]
        else:
            right_bi = [x for x in self.bi_list[-200:] if x['dt'] >= self.xd_list[-1]['dt']]
        xd_p = []
        bi_d = [x for x in right_bi if x['fx_mark'] == 'd']
        bi_g = [x for x in right_bi if x['fx_mark'] == 'g']
        for i in range(1, len(bi_d)-2):
            d1, d2, d3 = bi_d[i-1: i+2]
            if d1['bi'] > d2['bi'] < d3['bi']:
                xd_p.append(d2)
        for j in range(1, len(bi_g)-2):
            g1, g2, g3 = bi_g[j-1: j+2]
            if g1['bi'] < g2['bi'] > g3['bi']:
                xd_p.append(g2)

        xd_p = sorted(xd_p, key=lambda x: x['dt'], reverse=False)
        for xp in xd_p:
            xd = dict(xp)
            xd['xd'] = xd.pop('bi')
            last_xd = self.xd_list[-1]
            if last_xd['fx_mark'] == xd['fx_mark']:
                if (last_xd['fx_mark'] == 'd' and last_xd['xd'] > xd['xd']) \
                        or (last_xd['fx_mark'] == 'g' and last_xd['xd'] < xd['xd']):
                    if self.verbose:
                        print("更新线段标记：from {} to {}".format(last_xd, xd))
                    self.xd_list[-1] = xd
            else:
                if (last_xd['fx_mark'] == 'd' and last_xd['xd'] > xd['xd']) \
                        or (last_xd['fx_mark'] == 'g' and last_xd['xd'] < xd['xd']):
                    continue

                bi_inside = [x for x in right_bi if last_xd['dt'] <= x['dt'] <= xd['dt']]
                if len(bi_inside) < 4:
                    if self.verbose:
                        print("{} - {} 之间笔标记数量少于4，跳过".format(last_xd['dt'], xd['dt']))
                    continue
                else:
                    if len(bi_inside) > 4:
                        if self.verbose:
                            print("新增线段标记（笔标记数量大于4）：{}".format(xd))
                        self.xd_list.append(xd)
                    else:
                        bi_r = [x for x in right_bi if x['dt'] >= xd['dt']]
                        assert bi_r[1]['fx_mark'] == bi_inside[-2]['fx_mark']
                        # 第一种情况：没有缺口
                        if (bi_r[1]['fx_mark'] == "g" and bi_r[1]['bi'] > bi_inside[-3]['bi']) \
                                or (bi_r[1]['fx_mark'] == "d" and bi_r[1]['bi'] < bi_inside[-3]['bi']):
                            if self.verbose:
                                print("新增线段标记（第一种情况）：{}".format(xd))
                            self.xd_list.append(xd)
                        # 第二种情况：有缺口
                        else:
                            if (bi_r[1]['fx_mark'] == "g" and bi_r[1]['bi'] < bi_inside[-2]['bi']) \
                                    or (bi_r[1]['fx_mark'] == "d" and bi_r[1]['bi'] > bi_inside[-2]['bi']):
                                if self.verbose:
                                    print("新增线段标记（第二种情况）：{}".format(xd))
                                self.xd_list.append(xd)

        if (self.xd_list[-1]['fx_mark'] == 'd' and self.kline_new[-1]['low'] < self.xd_list[-1]['xd']) \
                or (self.xd_list[-1]['fx_mark'] == 'g' and self.kline_new[-1]['high'] > self.xd_list[-1]['xd']):
            if self.verbose:
                print("最后一个线段标记无效，{}".format(self.xd_list[-1]))
            self.xd_list.pop(-1)

    def update(self, k):
        """更新分析结果

        :param k: dict
            单根K线对象，样例如下
            {'symbol': '000001.SH',
             'dt': Timestamp('2020-07-16 15:00:00'),
             'open': 3356.11,
             'close': 3210.1,
             'high': 3373.53,
             'low': 3209.76,
             'vol': 486366915.0}
        """
        if self.verbose:
            print("=" * 100)
            print("输入新K线：{}".format(k))
        if not self.kline_raw or k['open'] != self.kline_raw[-1]['open']:
            self.kline_raw.append(k)
        else:
            if self.verbose:
                print("输入K线处于未完成状态，更新：replace {} with {}".format(self.kline_raw[-1], k))
            self.kline_raw[-1] = k

        self._update_ta()
        self._update_kline_new()
        self._update_fx_list()
        self._update_bi_list()
        self._update_xd_list()

        self.end_dt = self.kline_raw[-1]['dt']
        self.latest_price = self.kline_raw[-1]['close']

        # 根据最大原始K线序列长度限制分析结果长度
        if len(self.kline_raw) > self.max_raw_len:
            self.kline_raw = self.kline_raw[-self.max_raw_len:]
            self.ma = self.ma[-self.max_raw_len:]
            self.macd = self.macd[-self.max_raw_len:]
            self.kline_new = self.kline_new[-self.max_raw_len:]
            self.fx_list = self.fx_list[-(self.max_raw_len//2):]
            self.bi_list = self.bi_list[-(self.max_raw_len//4):]
            self.xd_list = self.xd_list[-(self.max_raw_len//8):]

        if self.verbose:
            print("更新结束\n\n")

    def to_df(self, ma_params=(5, 20), use_macd=False, max_count=1000):
        """整理成 df 输出

        :param ma_params: tuple of int
            均线系统参数
        :param use_macd: bool
        :param max_count: int
        :return: pd.DataFrame
        """
        bars = self.kline_raw[-max_count:]
        fx_list = {x["dt"]: {"fx_mark": x["fx_mark"], "fx": x['fx']} for x in self.fx_list[-(max_count // 2):]}
        bi_list = {x["dt"]: {"fx_mark": x["fx_mark"], "bi": x['bi']} for x in self.bi_list[-(max_count // 4):]}
        xd_list = {x["dt"]: {"fx_mark": x["fx_mark"], "xd": x['xd']} for x in self.xd_list[-(max_count // 8):]}
        results = []
        for k in bars:
            k['fx_mark'], k['fx'], k['bi'], k['xd'] = "o", None, None, None
            fx_ = fx_list.get(k['dt'], None)
            bi_ = bi_list.get(k['dt'], None)
            xd_ = xd_list.get(k['dt'], None)
            if fx_:
                k['fx_mark'] = fx_["fx_mark"]
                k['fx'] = fx_["fx"]

            if bi_:
                k['bi'] = bi_["bi"]

            if xd_:
                k['xd'] = xd_["xd"]

            results.append(k)
        df = pd.DataFrame(results)
        for p in ma_params:
            df.loc[:, "ma{}".format(p)] = ta.SMA(df.close.values, p)
        if use_macd:
            diff, dea, macd = ta.MACD(df.close.values)
            df.loc[:, "diff"] = diff
            df.loc[:, "dea"] = diff
            df.loc[:, "macd"] = diff
        return df

    def to_html(self, file_html="kline.html", width="1400px", height="680px"):
        """保存成 html

        :param file_html: str
            html文件名
        :param width: str
            页面宽度
        :param height: str
            页面高度
        :return:
        """
        plot_kline(self, file_html=file_html, width=width, height=height)

    def to_image(self, file_image, mav=(5, 20, 120, 250), max_k_count=1000, dpi=50):
        """保存成图片

        :param file_image: str
            图片名称，支持 jpg/png/svg 格式，注意后缀
        :param mav: tuple of int
            均线系统参数
        :param max_k_count: int
            设定最大K线数量，这个值越大，生成的图片越长
        :param dpi: int
            图片分辨率
        :return:
        """
        plot_ka(self, file_image=file_image, mav=mav, max_k_count=max_k_count, dpi=dpi)

    def is_bei_chi(self, zs1, zs2, mode="bi", adjust=0.9):
        """判断 zs1 对 zs2 是否有背驰

        注意：力度的比较，并没有要求两段走势方向一致；但是如果两段走势之间存在包含关系，这样的力度比较是没有意义的。

        :param zs1: dict
            用于比较的走势，通常是最近的走势，示例如下：
            zs1 = {"start_dt": "2020-02-20 11:30:00", "end_dt": "2020-02-20 14:30:00", "direction": "up"}
        :param zs2: dict
            被比较的走势，通常是较前的走势，示例如下：
            zs2 = {"start_dt": "2020-02-21 11:30:00", "end_dt": "2020-02-21 14:30:00", "direction": "down"}
        :param mode: str
            default `bi`, optional value [`xd`, `bi`]
            xd  判断两个线段之间是否存在背驰
            bi  判断两笔之间是否存在背驰
        :param adjust: float
            调整 zs2 的力度，建议设置范围在 0.6 ~ 1.0 之间，默认设置为 0.9；
            其作用是确保 zs1 相比于 zs2 的力度足够小。
        :return: bool
        """
        assert zs1["start_dt"] > zs2["end_dt"], "zs1 必须是最近的走势，用于比较；zs2 必须是较前的走势，被比较。"
        assert zs1["start_dt"] < zs1["end_dt"], "走势的时间区间定义错误，必须满足 start_dt < end_dt"
        assert zs2["start_dt"] < zs2["end_dt"], "走势的时间区间定义错误，必须满足 start_dt < end_dt"

        min_dt = min(zs1["start_dt"], zs2["start_dt"])
        max_dt = max(zs1["end_dt"], zs2["end_dt"])
        macd_ = [x for x in self.macd if x['dt'] >= min_dt]
        macd_ = [x for x in macd_ if max_dt >= x['dt']]
        k1 = [x for x in macd_ if zs1["end_dt"] >= x['dt'] >= zs1["start_dt"]]
        k2 = [x for x in macd_ if zs2["end_dt"] >= x['dt'] >= zs2["start_dt"]]

        bc = False
        if mode == 'bi':
            macd_sum1 = sum([abs(x['macd']) for x in k1])
            macd_sum2 = sum([abs(x['macd']) for x in k2])
            # print("bi: ", macd_sum1, macd_sum2)
            if macd_sum1 < macd_sum2 * adjust:
                bc = True

        elif mode == 'xd':
            assert zs1['direction'] in ['down', 'up'], "走势的 direction 定义错误，可取值为 up 或 down"
            assert zs2['direction'] in ['down', 'up'], "走势的 direction 定义错误，可取值为 up 或 down"

            if zs1['direction'] == "down":
                macd_sum1 = sum([abs(x['macd']) for x in k1 if x['macd'] < 0])
            else:
                macd_sum1 = sum([abs(x['macd']) for x in k1 if x['macd'] > 0])

            if zs2['direction'] == "down":
                macd_sum2 = sum([abs(x['macd']) for x in k2 if x['macd'] < 0])
            else:
                macd_sum2 = sum([abs(x['macd']) for x in k2 if x['macd'] > 0])

            # print("xd: ", macd_sum1, macd_sum2)
            if macd_sum1 < macd_sum2 * adjust:
                bc = True

        else:
            raise ValueError("mode value error")

        return bc

    def get_sub_section(self, start_dt: datetime, end_dt: datetime, mode="bi"):
        """获取子区间

        :param start_dt: datetime
            子区间开始时间
        :param end_dt: datetime
            子区间结束时间
        :param mode: str
            需要获取的子区间对象类型，可取值 ['k', 'fx', 'bi', 'xd']
        :return: list of dict
        """
        raise NotImplementedError

