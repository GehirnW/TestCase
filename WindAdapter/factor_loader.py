# -*- coding: utf-8 -*-

import re

import pandas as pd

from WindAdapter.data_provider import WindDataProvider
from WindAdapter.enums import FreqType
from WindAdapter.enums import Header
from WindAdapter.enums import OutputFormat
from WindAdapter.helper import WindQueryHelper
from WindAdapter.utils import date_convert_2_str
from WindAdapter.utils import py_assert

WIND_QUERY_HELPER = WindQueryHelper()
WIND_DATA_PROVIDER = WindDataProvider()


class FactorLoader:
    def __init__(self, start_date, end_date, factor_name, **kwargs):
        self._start_date = start_date
        self._end_date = end_date
        self._factor_name = factor_name
        self._sec_id = kwargs.get('sec_id', 'fulla')
        self._freq = kwargs.get('freq', FreqType.EOM)
        self._tenor = kwargs.get('tenor', None)
        self._output_data_format = kwargs.get('output_data_format', OutputFormat.MULTI_INDEX_DF)
        self._is_index = kwargs.get('is_index', True)

    @staticmethod
    def _concat_industry_params(factor_name, ret):
        if factor_name[:-1] == 'INDUSTRY_WEIGHT_C' or factor_name[:-1] == 'sw_c':
            ret += ';industryType=' + filter(str.isdigit, str(factor_name))
        return ret

    @staticmethod
    def _merge_query_params(params, date=None):
        ret = ''
        for index, value in params.iteritems():
            if not pd.isnull(value):
                if index == Header.TENOR:
                    py_assert(date is not None, ValueError, 'date must given if tenor is not None')
                    unit = ''.join(re.findall('[0-9]+', params[Header.TENOR]))
                    freq = FreqType(params[Header.TENOR][len(unit):])
                    ret += 'startDate=' + WindDataProvider.advance_date(date, unit, freq).strftime(
                        '%Y%m%d') + ';endDate=' + date + ';'
                else:
                    ret += (index + '=' + str(value) + ';')
        ret = ret[:-1]
        ret = FactorLoader._concat_industry_params(params.name, ret)
        return ret

    @staticmethod
    def _get_enum_value(enum_var):
        if isinstance(enum_var, FreqType):
            return enum_var.value
        elif isinstance(enum_var, basestring):
            return enum_var
        else:
            raise TypeError('Wring type of enum variable {0}'.format(enum_var))

    def _get_sec_id(self, date):
        if isinstance(self._sec_id, basestring):
            sec_id = WIND_DATA_PROVIDER.get_universe(self._sec_id, date=date) \
                if self._is_index else self._sec_id
        elif isinstance(self._sec_id, list):
            sec_id = self._sec_id
        else:
            raise TypeError('FactorLoader._get_sec_id: sec_id must be either list of string')

        return sec_id

    def _retrieve_data(self, main_params, extra_params, output_data_format):
        output_data = pd.DataFrame()
        api = main_params[Header.API]
        dates = WIND_DATA_PROVIDER.biz_days_list(start_date=self._start_date,
                                                 end_date=self._end_date,
                                                 freq=self._freq)
        for date in dates:
            date = date_convert_2_str(date)

            sec_id = WIND_DATA_PROVIDER.get_universe(self._sec_id, date=date) \
                if self._is_index else self._sec_id
            if api == 'w.wsd':
                merged_extra_params = self._merge_query_params(extra_params)
                raw_data = WIND_DATA_PROVIDER.query_data(api=api,
                                                         sec_id=sec_id,
                                                         indicator=main_params[Header.INDICATOR],
                                                         extra_params=merged_extra_params,
                                                         start_date=date,
                                                         end_date=date)

            elif api == 'w.wss':
                py_assert(not pd.isnull(extra_params[Header.TENOR]), ValueError,
                          'tenor must be given for query factor {0}'.format(self._factor_name))
                merged_extra_params = self._merge_query_params(extra_params, date=date)
                raw_data = WIND_DATA_PROVIDER.query_data(api=api,
                                                         sec_id=sec_id,
                                                         indicator=main_params[Header.INDICATOR],
                                                         extra_params=merged_extra_params)
            else:
                raise ValueError('FactorLoader._retrieve_data: unacceptable value of parameter api')
            tmp = WIND_QUERY_HELPER.reformat_wind_data(raw_data=raw_data,
                                                       date=date,
                                                       output_data_format=output_data_format)
            output_data = pd.concat([output_data, tmp], axis=0)

        return output_data

    def _load_single_factor(self):
        main_params, extra_params = WIND_QUERY_HELPER.get_query_params(self._factor_name)
        extra_params[Header.TENOR.value] = self._get_enum_value(self._tenor) if self._tenor is not None else None
        extra_params[Header.FREQ.value] = self._get_enum_value(self._freq)
        ret = self._retrieve_data(main_params=main_params,
                                  extra_params=extra_params,
                                  output_data_format=self._output_data_format)
        return ret

    def load_data(self):
        if self._factor_name[:-3] == 'INDUSTRY_WEIGHT':
            ret = self._load_industry_weight()
        else:
            ret = self._load_single_factor()
        return ret

    def _load_industry_weight(self):
        ret = pd.DataFrame()
        dates = WIND_DATA_PROVIDER.biz_days_list(start_date=self._start_date,
                                                 end_date=self._end_date,
                                                 freq=self._freq)
        extra_params = FactorLoader._concat_industry_params(self._factor_name, "")
        for date in dates:
            date = date_convert_2_str(date)
            index_info = WIND_DATA_PROVIDER.get_universe(self._sec_id, date=date, output_weight=True)
            class_info = WIND_DATA_PROVIDER.query_data(api='w.wsd',
                                                       sec_id=index_info[1],
                                                       indicator='indexcode_sw',
                                                       extra_params=extra_params,
                                                       start_date=date,
                                                       end_date=date)
            industry_weight = pd.DataFrame(data={'sec_id': index_info[1],
                                                 'class_id': class_info.Data[0],
                                                 'sec_weight': index_info[3]},
                                           index=index_info[0])

            tmp = industry_weight.groupby('class_id').sum().T
            tmp.index = [date]
            tmp = WIND_QUERY_HELPER.convert_2_multi_index(tmp) \
                if self._output_data_format == OutputFormat.MULTI_INDEX_DF else tmp
            ret = ret.append(tmp)
        return ret
