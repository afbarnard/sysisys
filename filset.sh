#!/bin/bash
#
# Treat files as sets of lines

# Copyright (c) 2018 Aubrey Barnard.  This is free software released
# under the MIT License.  See `LICENSE.txt` for details.

# TODO "-" indicates a set on stdin
# TODO add length?
# TODO add equality?
# TODO "make" as a special case of union?

# Exit immediately on errors
set -e

# Log the given arguments as a message
function log() {
    true
    #echo "$(date +'%FT%T') filset: ${@}" >&2
}

# Print the given arguments as a message and die
function die() {
    echo "filset: Error: ${@}" >&2
    exit 1
}

# Backup the given file
function backup() {
    log "backup(${@})"
    if [[ -e "${1}" ]]; then
        cp --archive "${1}" "${1}.$(date +'%Y%m%d-%H%M%S')"
    fi
}

# Print each argument on its own line
function args_as_lines() {
    for arg; do
        echo "${arg}"
    done
}

# Add all the subsequent items to the first set
function add() {
    log "add(${@})"
    master="${1}"
    shift
    union "${master}" <(args_as_lines "${@}")
}

# Delete all the subsequent items from the first set
function delete() {
    log "delete(${@})"
    master="${1}"
    shift
    subtract "${master}" <(args_as_lines "${@}")
}

# Membership: does the first set have all the subsequent items? (which
# is just intersection)
function has() {
    log "has(${@})"
    master="${1}"
    shift
    intersect "${master}" <(args_as_lines "${@}")
}

# Union all the given sets
function union() {
    log "union(${@})"
    if [[ ${#} -lt 1 ]]; then
        die "union: No sets to union"
    fi
    sort --unique "${@}"
}

# Intersect all the given sets
function intersect() {
    log "intersect(${@})"
    if [[ ${#} -lt 1 ]]; then
        die "intersect: No sets to intersect"
    fi
    # Combine sets and yield duplicates.  Make sure all the sets have
    # unique items first.
    for fileset; do
        sort --unique "${fileset}"
    done | sort | uniq --repeated
}

# Subtract the intersection from the union of all the given sets
# (symmetric difference)
function symmetric_difference() {
    log "symmetric_difference(${@})"
    if [[ ${#} -lt 1 ]]; then
        die "symmetric_difference: No sets to difference"
    fi
    # Combine sets and yield uniques.  Make sure all the sets have
    # unique items first.
    for fileset; do
        sort --unique "${fileset}"
    done | sort | uniq --unique
}

# Subtract all the given sets from the first set
function subtract() {
    log "subtract(${@})"
    if [[ ${#} -lt 1 ]]; then
        die "subtract: No sets to subtract"
    fi
    intersect "${1}" <(symmetric_difference "${@}")
}

# Map CLI set operations to functions
declare -A op_map
op_map=(
    [add]=add
    [del]=delete
    [has]=has
    [union]=union
    [inter]=intersect
    [symdif]=symmetric_difference
    [minus]=subtract
)

# Executes the given set operation and either stores the result or lets
# the result go to stdout
function do_set_op() {
    log "do_set_op(${@})"
    operation="${1}"
    result="${2}"
    master="${3}"
    shift 3
    # Default master set to `/dev/null` for those operations that
    # require a master set
    if [[ -z "${master}" && ${operation} =~ ^(add|del|has|minus)$ ]]; then
        master=/dev/null
    fi
    # Execute the operation, saving the result or letting it go to
    # stdout as requested
    if [[ -n "${result}" ]]; then
        # Use a temp file to hold the result so as not to clobber a
        # result file that is also among the arguments
        tmp_file=$(mktemp)
        if [[ -n "${master}" ]]; then
            ${op_map[${operation}]} "${master}" "${@}" > "${tmp_file}"
        else
            ${op_map[${operation}]} "${@}" > "${tmp_file}"
        fi
        mv "${tmp_file}" "${result}"
    else
        if [[ -n "${master}" ]]; then
            ${op_map[${operation}]} "${master}" "${@}"
        else
            ${op_map[${operation}]} "${@}"
        fi
    fi
}

# Processes args and carries out set operations specified therein
function main() {
    log "main(${@})"
    # File that stores the result set.  If not specified, the result
    # goes to stdout.
    result=
    # File set that operations are relative to (if applicable).  If not
    # specified and necessary, the default is `/dev/null`.
    master=
    # Whether to backup the result set
    make_backup=
    # Operation to carry out
    op=
    while [[ ${#} -gt 0 ]]; do
        case "${1}" in
            (-b)
                make_backup=yes
                ;;
            ("="|"+=")
                if [[ -z "${master}" ]]; then
                    die "No result filename before '${1}'"
                fi
                result="${master}"
                if [[ "${1}" == "=" ]]; then
                    master=
                fi
                ;;
            (add|del|has|union|inter|symdif|minus)
                # Make a backup of the result file if requested
                if [[ -n "${make_backup}" && -n "${result}" ]]; then
                    backup "${result}"
                fi
                # Do the set operation
                op=${1}
                shift
                do_set_op "${op}" "${result}" "${master}" "${@}"
                break
                ;;
            (*)
                # An unrecognized argument is the master set as long as
                # the master set is not set
                if [[ -z "${master}" ]]; then
                    master="${1}"
                else
                    die "Unrecognized set operation: ${1}"
                fi
                ;;
        esac
        # Consume argument
        shift
    done
    if [[ -z "${op}" ]]; then
        die "No operation specified"
    fi
}

# Execute main
main "${@}"
