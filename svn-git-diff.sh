#!/usr/bin/bash

# Script to use as a custom diff for Subversion that invokes Git's diff.

# Copyright (c) 2025 Aubrey Barnard.
#
# This is free software released under the MIT License.  See
# `LICENSE.txt` for details.

# Exit immediately on errors
set -e

# Subversion (1.14) passes its diff command:
# 1. Any options specified by '-x'.  When '-x' is not given, the option
#    '-u' is passed.
# 2. Two '-L' label options with a single label argument each.
# 3. The two files to diff, as absolute paths.
#
# For example, `svn diff --diff-cmd svn-word-diff.sh template.txt`
# results in the following CLI arguments to the diff command:
#
#     -u -L 'template.txt	(revision 5744)' -L 'template.txt	(working copy)' /home/[...]/.svn/pristine/34/34b52966834e94083aec8a6f35dd94067a7f2ad7.svn-base /home/[...]/template.txt
#
# Adding '-x --word-diff' to the above replaces the initial '-u' with
# '--word-diff'.  Thus, if you still want to include '-u', then you must
# add `-x '-u --word-diff'`.

#echo "${@}"

# Arrays to hold extracted arguments
declare -a labels files

# An array of all other arguments
declare -a args

# Parse the arguments
while [[ ${#} -gt 0 ]]; do
    case "${1}" in
        # Label options
        (-L)
            # Replace tab with 4 spaces
            labels+=( "${2/	/    }" )
            shift 2
            ;;
        # Other options
        (-*)
            args+=( "${1}" )
            shift
            ;;
        # Other arguments, which are assumed to be files
        (*)
            files+=( "${1}" )
            shift
            ;;
    esac
done

#echo "labels[${#labels[@]}]: ${labels[@]}"
#echo "files[${#files[@]}]: ${files[@]}"
#echo "args[${#args[@]}]: ${args[@]}"

# Check the number of labels
if [[ ${#labels[@]} -ne 2 ]]; then
    echo -e "${0}: Error: Expected 2 labels, but got ${#labels[@]}: [${labels[@]}]" >&2
    exit 2
fi
# Check the number of files
if [[ ${#files[@]} -ne 2 ]]; then
    echo -e "${0}: Error: Expected 2 files, but got ${#files[@]}: [${files[@]}]" >&2
    exit 2
fi

# Assemble and run the command
git --no-pager diff --no-index "${args[@]}" --src-prefix "${labels[0]}: /" --dst-prefix "${labels[1]}: /" "${files[@]}"
