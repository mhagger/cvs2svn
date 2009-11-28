# (Be in -*- python -*- mode.)
#
# ====================================================================
# Copyright (c) 2000-2009 CollabNet.  All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution.  The terms
# are also available at http://subversion.tigris.org/license-1.html.
# If newer versions of this license are posted there, you may use a
# newer version instead, at your option.
#
# This software consists of voluntary contributions made by many
# individuals.  For exact contribution history, see the revision
# history and logs, available at http://cvs2svn.tigris.org/.
# ====================================================================

"""Functions to sort large files.

The functions in this module were originally downloaded from the
following URL:

    http://code.activestate.com/recipes/466302/

It was apparently submitted by Nicolas Lehuen on Tue, 17 Jan 2006.
According to the terms of service of that website, the code is usable
under the MIT license.

"""


import os
import heapq
import itertools
import tempfile


# The buffer size to use for open files:
BUFSIZE = 64 * 1024


def merge(iterables, key=None):
  if key is None:
    key = lambda x : x

  values = []

  for index, iterable in enumerate(iterables):
    try:
      iterator = iter(iterable)
      value = iterator.next()
    except StopIteration:
      pass
    else:
      heapq.heappush(values, ((key(value), index, value, iterator)))

  while values:
    k, index, value, iterator = heapq.heappop(values)
    yield value
    try:
      value = iterator.next()
    except StopIteration:
      pass
    else:
      heapq.heappush(values, (key(value), index, value, iterator))


def sort_file(input, output, key=None, buffer_size=32000, tempdirs=[]):
  # Create an iterator that will choose directories to hold the
  # temporary files:
  if tempdirs:
    tempdirs = itertools.cycle(tempdirs)
  else:
    tempdirs = itertools.repeat(tempfile.gettempdir())

  filenames = []
  try:
    input_file = file(input, 'rb', BUFSIZE)
    try:
      input_iterator = iter(input_file)
      while True:
        current_chunk = list(itertools.islice(input_iterator, buffer_size))
        if not current_chunk:
          break
        current_chunk.sort(key=key)
        (fd, filename) = tempfile.mkstemp(
            '', 'sort%06i' % (len(filenames),), tempdirs.next(), False
            )
        filenames.append(filename)
        os.close(fd)
        f = open(filename, 'w+b', BUFSIZE)
        f.writelines(current_chunk)
        f.close()
    finally:
      input_file.close()

    output_file = file(output, 'wb', BUFSIZE)
    try:
      chunks = []
      try:
        for filename in filenames:
          chunks.append(open(filename, 'rb', BUFSIZE))
        output_file.writelines(merge(chunks, key))
      finally:
        for chunk in chunks:
          try:
            chunk.close()
          except:
            pass
    finally:
      output_file.close()
  finally:
    for filename in filenames:
      try:
        os.remove(filename)
      except:
        pass


