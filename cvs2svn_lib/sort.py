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

  chunks = []
  try:
    input_file = file(input, 'rb', 64*1024)
    try:
      input_iterator = iter(input_file)
      while True:
        current_chunk = list(itertools.islice(input_iterator, buffer_size))
        if not current_chunk:
          break
        current_chunk.sort(key=key)
        (fd, filename) = tempfile.mkstemp(
            '', 'sort%06i' % (len(chunks),), tempdirs.next(), False
            )
        os.close(fd)
        output_chunk = open(filename, 'w+b', 64*1024)
        chunks.append(output_chunk)
        output_chunk.writelines(current_chunk)
        output_chunk.flush()
        output_chunk.seek(0)
    finally:
      input_file.close()

    output_file = file(output, 'wb', 64*1024)
    try:
      output_file.writelines(merge(chunks, key))
    finally:
      output_file.close()
  finally:
    for chunk in chunks:
      try:
        chunk.close()
        os.remove(chunk.name)
      except:
        pass


