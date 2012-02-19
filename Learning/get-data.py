
# -*- coding: utf-8 -*-

import feedparser, math
from BeautifulSoup import BeautifulSoup
from nltk import word_tokenize
from nltk.stem.porter import PorterStemmer
import nltk.data
from itertools import groupby
import json, time, collections, sys
from mixpanel import Mixpanel
from secrets import MIXPANEL
from datetime import datetime
from pymongo import Connection

import functools
import cPickle
def memoize(fctn):
    memory = {}
    @functools.wraps(fctn)
    def memo(*args,**kwargs):
        haxh = cPickle.dumps((args, sorted(kwargs.iteritems())))

        if haxh not in memory:
            memory[haxh] = fctn(*args,**kwargs)

        return memory[haxh]
    if memo.__doc__:
        memo.__doc__ = "\n".join([memo.__doc__,"This function is memoized."])
    return memo

from hyphen import Hyphenator

@memoize
def syllables(word):
    try:
        syllables = Hyphenator('hyph_en_GB.dic',
                               directory=u'/usr/share/hyphen/').syllables(unicode(word))
    except ValueError:
        syllables = []
    return syllables if len(syllables) > 0 else [unicode(word)]

@memoize
def words(entry):
    if type(entry) == unicode or type(entry) == str:
        words = entry.split()
    else:
        words = entry.content[0].value.split()

    return filter(lambda w: len(w) > 0,
                  [w.strip("0123456789!:,.?(){}[]") for w in words])

@memoize
def sentences(entry):
    sent_detector = nltk.data.load('tokenizers/punkt/english.pickle')
    if type(entry) == unicode or type(entry) == str:
        return sent_detector.tokenize(entry)
    else:
        return sent_detector.tokenize(entry.content[0].value)

@memoize
def paragraphs(entry):
    if type(entry) == unicode or type(entry) == str:
        ps = entry.split('\n\n')
    else:
        ps = entry.content[0].raw.split('\n\n')

    def pretty(p):
        p = u'' if p.startswith('[') else p # image captions
        return ''.join(BeautifulSoup(p).findAll(text=True))
    return [pretty(p)
            for p in ps if '<h2>' not in p]

def cleanup(data):
    def cleaned(entry):
        entry.counts = {'h2': entry.content[0].value.count("<h2>"),
                        'p': entry.content[0].value.count("\n\n")-entry.content[0].value.count("</h2>\n\n"),
                        'img': entry.content[0].value.count('<img')}

        entry.content[0].raw = entry.content[0].value
        entry.content[0].value = ''.join(BeautifulSoup(entry.content[0].value).findAll(text=True))
        return entry
    data.entries = map(cleaned, data.entries)
    return data

def word_length(entry):
    @memoize
    def average():
        return sum([len(syllables(w)) for w in words(entry)])\
                   /float(len(words(entry)))
    def deviation():
        return math.sqrt(sum([(len(syllables(w))-average())**2 for w in words(entry)])\
                             /float(len(words(entry))))

    return (round(average(), 2), round(deviation(), 2))

def sentence_length(entry):
    @memoize
    def average():
        return sum([len(words(s))*1.0 for s in sentences(entry)])\
                   /float(len(sentences(entry)))
    def deviation():
        return math.sqrt(sum([(len(words(s))-average())**2 for s in sentences(entry)])\
                             /float(len(sentences(entry))))

    return (round(average(), 2), round(deviation(), 2))

def paragraph_length(entry):
    @memoize
    def average():
        return sum([len(sentences(p))*1.0 for p in paragraphs(entry)])\
                   /float(len(paragraphs(entry)))

    def deviation():
        return math.sqrt(sum([(len(sentences(p))-average())**2
                              for p in paragraphs(entry)])\
                             /float(len(paragraphs(entry))))

    return (round(average(), 2), round(deviation(), 2))

def yule(entry):
    # yule's I measure (the inverse of yule's K measure)
    # higher number is higher diversity - richer vocabulary
    stemmer = PorterStemmer()
    d = collections.Counter([stemmer.stem(w).lower() for w in words(entry)])

    M1 = float(len(d))
    M2 = sum([len(list(g))*(freq**2) for freq,g in groupby(sorted(d.values()))])

    try:
        return round((M1*M1)/(M2-M1), 2)
    except ZeroDivisionError:
        return 0

def flesch_kincaid(entry):
    #http://en.wikipedia.org/wiki/Flesch%E2%80%93Kincaid_readability_test
    def syllable_count():
        return sum([len(syllables(w)) for w in words(entry)])

    try:
        return round(206.835-1.015*(
                               len(words(entry))/float(len(sentences(entry)))
                               )-84.6*(
                                   syllable_count()/float(len(words(entry)))
                               ),
                     2)
    except ZeroDivisionError:
        return 0


mx = Mixpanel(MIXPANEL['api_key'], MIXPANEL['api_secret'])

def conversions(entry):
    try:
        date = datetime.strptime(entry.wp_post_date_gmt,
                                 '%Y-%m-%d %H:%M:%S')
    except ValueError:
        raise NoConversions()

    funnel = mx.request(['funnels'],
                        {'funnel_id': 6517,
                         'from_date': date.strftime('%Y-%m-%d'),
                         'where': 'url=='+entry.link})

    if 'error' in funnel.keys():
        print funnel
        raise NoConversions()

    def stitch(*iterables):
        return [(iterables[0][i][0], sum([l[i][1] for l in iterables]))
                for i in xrange(len(iterables[0]))]

    def one(z):
        d = dict(stitch(*[[b for b in zip(a.keys(), a.values()) if b[0] in ['count', 'step_conv_ratio', 'overall_conv_ratio']] for a in z]))

        d['overall_conv_ratio'] = d['overall_conv_ratio']/len(funnel['meta']['dates'])
        d['step_conv_ratio'] = d['step_conv_ratio']/len(funnel['meta']['dates'])
        return d

    conversions =  map(one,
                       zip(*[v['steps'][:entry['counts']['p']]
                             for v in funnel['data'].values()]))

    def average(c):
        return sum([(i+1)*c[i]['overall_conv_ratio']
                    for i in xrange(len(c))])/float(len(c))

    return {'average': round(average(conversions), 2),
            'finishes': round(conversions[-1]['overall_conv_ratio'], 2)}

def extract_data(entry):
    data = {'complexity': {},
            'length': {},
            'style': {},
            'readership': {}}

    data['complexity'].update({'flesch_kincaid': flesch_kincaid(entry),
                               'yule': yule(entry),
                               'word_len': word_length(entry),
                               'sentence_len': sentence_length(entry),
                               'paragraph_len': paragraph_length(entry)})
    data['length'].update({'words': len(words(entry)),
                           'sentences': len(sentences(entry)),
                           'paragraphs': entry['counts']['p']})
    data['style'].update(entry['counts'])
    data['readership'] = conversions(entry)

    return data

class NoConversions(Exception):
    pass

if __name__ == "__main__":
    data = feedparser.parse(sys.argv[1])
    data = cleanup(data)

    db = Connection().readership_data
    posts = db.posts
    readership = db.readership

    for entry in reversed(data.entries):
        try:
            d = extract_data(entry)
        except NoConversions:
            continue

        post = posts.insert({'title': entry.title,
                             'content': entry.content[0]['raw'],
                             'href': entry.links[0]['href'],
                             'time': datetime.strptime(entry.wp_post_date_gmt,
                                                       '%Y-%m-%d %H:%M:%S')})
        d['post'] = post
        readership.insert(d)

        print datetime.strptime(entry.wp_post_date_gmt,
                                '%Y-%m-%d %H:%M:%S')
