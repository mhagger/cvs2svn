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
import shutil
import heapq
import itertools
import tempfile


# The buffer size to use for open files:
BUFSIZE = 64 * 1024


def get_default_max_merge():
  """Return the default maximum number of files to merge at once."""

  # The maximum number of files to merge at once.  This number cannot
  # be unlimited because there are operating system restrictions on
  # the number of files that a process can have open at once.  So...
  try:
    # If this constant is available via sysconf, we use half the
    # number available to the process as a whole.
    _SC_OPEN_MAX = os.sysconf('SC_OPEN_MAX')
    if _SC_OPEN_MAX == -1:
      # This also indicates an error:
      raise ValueError()
    return min(_SC_OPEN_MAX // 2, 100)
  except:
    # Otherwise, simply limit the number to this constant, which will
    # hopefully be OK on all operating systems:
    return 50


DEFAULT_MAX_MERGE = get_default_max_merge()


def merge(iterables, key=None):
  """Merge (in the sense of mergesort) ITERABLES.

  Generate the output in order.  If KEY is specified, it should be a
  function that returns the sort key."""

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
      values.append((key(value), index, value, iterator))

  heapq.heapify(values)

  while values:
    k, index, value, iterator = heapq.heappop(values)
    yield value
    try:
      value = iterator.next()
    except StopIteration:
      pass
    else:
      heapq.heappush(values, (key(value), index, value, iterator))


def merge_files_onepass(input_filenames, output_filename, key=None):
  """Merge a number of input files into one output file.

  This is a merge in the sense of mergesort; namely, it is assumed
  that the input files are each sorted, and (under that assumption)
  the output file will also be sorted."""

  input_filenames = list(input_filenames)
  if len(input_filenames) == 1:
    shutil.move(input_filenames[0], output_filename)
  else:
    output_file = file(output_filename, 'wb', BUFSIZE)
    try:
      chunks = []
      try:
        for input_filename in input_filenames:
          chunks.append(open(input_filename, 'rb', BUFSIZE))
        output_file.writelines(merge(chunks, key))
      finally:
        for chunk in chunks:
          try:
            chunk.close()
          except:
            pass
    finally:
      output_file.close()


def _try_delete_files(filenames):
  """Try to remove the named files.  Ignore errors."""

  for filename in filenames:
    try:
      os.remove(filename)
    except:
      pass


def tempfile_generator(tempdirs=[]):
  """Yield filenames of temporary files."""

  # Create an iterator that will choose directories to hold the
  # temporary files:
  if tempdirs:
    tempdirs = itertools.cycle(tempdirs)
  else:
    tempdirs = itertools.repeat(tempfile.gettempdir())

  i = 0
  while True:
    (fd, filename) = tempfile.mkstemp(
        '', 'sort%06i-' % (i,), tempdirs.next(), False
        )
    os.close(fd)
    yield filename
    i += 1


def _merge_file_generation(
    input_filenames, delete_inputs, key=None,
    max_merge=DEFAULT_MAX_MERGE, tempfiles=None,
    ):
  """Merge multiple input files into fewer output files.

  This is a merge in the sense of mergesort; namely, it is assumed
  that the input files are each sorted, and (under that assumption)
  the output file will also be sorted.  At most MAX_MERGE input files
  will be merged at once, to avoid exceeding operating system
  restrictions on the number of files that can be open at one time.

  If DELETE_INPUTS is True, then the input files will be deleted when
  they are no longer needed.

  If temporary files need to be used, they will be created using the
  specified TEMPFILES tempfile generator.

  Generate the names of the output files."""

  if max_merge <= 1:
    raise ValueError('max_merge must be greater than one')

  if tempfiles is None:
    tempfiles = tempfile_generator()

  filenames = list(input_filenames)
  if len(filenames) <= 1:
    raise ValueError('It makes no sense to merge a single file')

  while filenames:
    group = filenames[:max_merge]
    del filenames[:max_merge]
    group_output = tempfiles.next()
    merge_files_onepass(group, group_output, key=key)
    if delete_inputs:
      _try_delete_files(group)
    yield group_output


def merge_files(
    input_filenames, output_filename, key=None, delete_inputs=False,
    max_merge=DEFAULT_MAX_MERGE, tempfiles=None,
    ):
  """Merge a number of input files into one output file.

  This is a merge in the sense of mergesort; namely, it is assumed
  that the input files are each sorted, and (under that assumption)
  the output file will also be sorted.  At most MAX_MERGE input files
  will be merged at once, to avoid exceeding operating system
  restrictions on the number of files that can be open at one time.

  If DELETE_INPUTS is True, then the input files will be deleted when
  they are no longer needed.

  If temporary files need to be used, they will be created using the
  specified TEMPFILES tempfile generator."""

  filenames = list(input_filenames)
  if not filenames:
    # Create an empty file:
    open(output_filename, 'wb').close()
  else:
    if tempfiles is None:
      tempfiles = tempfile_generator()
    while len(filenames) > max_merge:
      # Reduce the number of files by performing groupwise merges:
      filenames = list(
          _merge_file_generation(
              filenames, delete_inputs, key=key,
              max_merge=max_merge, tempfiles=tempfiles
              )
          )
      # After the first iteration, we are only working with temporary
      # files so they can definitely be deleted them when we are done
      # with them:
      delete_inputs = True

    # The last merge writes the results directly into the output
    # file:
    merge_files_onepass(filenames, output_filename, key=key)
    if delete_inputs:
      _try_delete_files(filenames)


def sort_file(
      input, output, key=None,
      buffer_size=32000, tempdirs=[], max_merge=DEFAULT_MAX_MERGE,
      ):
  tempfiles = tempfile_generator(tempdirs)

  filenames = []

  input_file = file(input, 'rb', BUFSIZE)
  try:
    try:
      input_iterator = iter(input_file)
      while True:
        current_chunk = list(itertools.islice(input_iterator, buffer_size))
        if not current_chunk:
          break
        current_chunk.sort(key=key)
        filename = tempfiles.next()
        filenames.append(filename)
        f = open(filename, 'w+b', BUFSIZE)
        try:
          f.writelines(current_chunk)
        finally:
          f.close()
    finally:
      input_file.close()

    merge_files(
        filenames, output, key=key,
        delete_inputs=True, max_merge=max_merge, tempfiles=tempfiles,
        )
  finally:
    _try_delete_files(filenames)


