# -*- coding: utf-8 -*-
from __future__ import unicode_literals, division, print_function, absolute_import
import urllib
import subprocess
import json
import os
import re

import requests
#from requests.auth import HTTPBasicAuth
from requests.auth import _basic_auth_str

from .compat.environ import *
from .compat.imports import urlencode
from .utils import String
from .http import Headers, Url


class HTTPClient(object):
    """A generic test client that can make endpoint requests"""
    timeout = 10

    def __init__(self, host, *args, **kwargs):
        self.host = Url(host)

        # these are the common headers that usually don't change all that much
        self.headers = Headers({
            "x-forwarded-for": "127.0.0.1",
            "user-agent": "Endpoints client",
        })

        if kwargs.get("json", False):
            self.headers.update({
                "content-type": "application/json",
            })

        headers = kwargs.get("headers", {})
        if headers:
            self.headers.update(headers)

    def get(self, uri, query=None, **kwargs):
        """make a GET request"""
        return self.fetch('get', uri, query, **kwargs)

    def post(self, uri, body=None, **kwargs):
        """make a POST request"""
        return self.fetch('post', uri, kwargs.pop("query", {}), body, **kwargs)

    def post_file(self, uri, body, files, **kwargs):
        """POST a file"""
        # requests doesn't actually need us to open the files but we do anyway because
        # if we don't then the filename isn't preserved, so we assume each string
        # value is a filepath
        for key in files.keys():
            if isinstance(files[key], basestring):
                files[key] = open(files[key], 'rb')
        kwargs["files"] = files

        # we ignore content type for posting files since it requires very specific things
        ct = self.headers.pop("content-type", None)
        ret = self.fetch('post', uri, {}, body, **kwargs)
        if ct:
            self.headers["content-type"] = ct

        # close all the files
        for fp in files.values():
            fp.close()
        return ret

    def delete(self, uri, query=None, **kwargs):
        """make a DELETE request"""
        return self.fetch('delete', uri, query, **kwargs)

    def fetch(self, method, uri, query=None, body=None, **kwargs):
        """
        wrapper method that all the top level methods (get, post, etc.) use to actually
        make the request
        """
        if not query: query = {}
        fetch_url = self.get_fetch_url(uri, query)

        args = [fetch_url]

        kwargs.setdefault("timeout", self.timeout)
        kwargs["headers"] = self.get_fetch_headers(method, kwargs.get("headers", {}))

        if body:
            if self.is_json(kwargs["headers"]):
                kwargs['json'] = self.get_fetch_body(body)
            else:
                kwargs['data'] = self.get_fetch_body(body)

        res = self.get_fetch_request(method, *args, **kwargs)
        #res = requests.request(method, *args, **kwargs)
        res = self.get_fetch_response(res)
        self.response = res
        return res

    def get_fetch_query(self, query_str, query):

        all_query = getattr(self, "query", {})
        if not all_query: all_query = {}
        if query:
            all_query.update(query)

        if all_query:
            more_query_str = urlencode(all_query, doseq=True)
            if query_str:
                query_str += '&{}'.format(more_query_str)
            else:
                query_str = more_query_str

        return query_str

    def get_fetch_host(self):
        return self.host.root

    def get_fetch_url(self, uri, query=None):
        if not isinstance(uri, basestring):
            # allow ["foo", "bar"] to be converted to "/foo/bar"
            uri = "/".join(uri)

        ret_url = uri
        if not re.match(r"^\S+://\S", uri):
            base_url = self.get_fetch_host()
            base_url = base_url.rstrip('/')
            query_str = ''
            if '?' in uri:
                i = uri.index('?')
                query_str = uri[i+1:]
                uri = uri[0:i]

            uri = uri.lstrip('/')
            query_str = self.get_fetch_query(query_str, query)
            if query_str:
                uri = '{}?{}'.format(uri, query_str)

            ret_url = '{}/{}'.format(base_url, uri)

        return ret_url

    def get_fetch_headers(self, method, headers):
        """merge class headers with passed in headers

        :param method: string, (eg, GET or POST), this is passed in so you can customize
            headers based on the method that you are calling
        :param headers: dict, all the headers passed into the fetch method
        :returns: passed in headers merged with global class headers
        """
        all_headers = self.headers.copy()
        if headers:
            all_headers.update(headers)
        return Headers(all_headers)

    def get_fetch_body(self, body):
        return body

    def get_fetch_request(self, method, fetch_url, *args, **kwargs):
        """This is handy if you want to modify the request right before passing it
        to requests, or you want to do something extra special customized

        :param method: string, the http method (eg, GET, POST)
        :param fetch_url: string, the full url with query params
        :param *args: any other positional arguments
        :param **kwargs: any keyword arguments to pass to requests
        :returns: a requests.Response compatible object instance
        """
        return requests.request(method, fetch_url, *args, **kwargs)

    def get_fetch_response(self, res):
        """the goal of this method is to make the requests object more endpoints like

        res -- requests Response -- the native requests response instance, we manipulate
            it a bit to make it look a bit more like the internal endpoints.Response object
        """
        res.code = res.status_code
        res.headers = Headers(res.headers)
        res._body = None
        res.body = ''
        body = res.content
        if body:
            if self.is_json(res.headers):
                res._body = res.json()
            else:
                res._body = body

            res.body = String(body, res.encoding)

        return res

    def is_json(self, headers):
        """return true if content_type is a json content type"""
        ret = False
        ct = headers.get("content-type", "").lower()
        if ct:
            ret = ct.lower().rfind("json") >= 0
        return ret

    def basic_auth(self, username, password):
        '''
        add basic auth to this client

        link -- http://stackoverflow.com/questions/6068674/

        username -- string
        password -- string
        '''
        self.headers['authorization'] = _basic_auth_str(username, password)
#         credentials = HTTPBasicAuth(username, password)
#         #credentials = base64.b64encode('{}:{}'.format(username, password)).strip()
#         auth_string = 'Basic {}'.format(credentials())
#         self.headers['authorization'] = auth_string

    def token_auth(self, access_token):
        """add bearer TOKEN auth to this client"""
        self.headers['authorization'] = 'Bearer {}'.format(access_token)

    def remove_auth(self):
        self.headers.pop('authorization', None)

    def set_version(self, version):
        self.headers["accept"] = "{};version={}".format(
            self.headers["content-type"],
            version
        )

