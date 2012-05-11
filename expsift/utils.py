# Parameters:
# - dir2prop_dict: Dictionary that maps directories to the set of all properties
#                  for that directory.
# Returns:
# - common props: The set of common properties for all the directories
# - unique_props: Dictionary that maps directories to the unique properties for
#                 that directory
def getCommonAndUniqueProperties(dir2prop_dict):

    # Find the common and unique properties for all directories
    # If there is only one directory, then all the properties enter the
    # common_props set and the unique_props set becomes empty. So we just add
    # the term 'properties=all_common' to the unique_props set in that case.
    common_props = set.intersection(*(dir2prop_dict.values()))
    unique_props = {}
    for directory, props in dir2prop_dict.iteritems():
        unique = props - common_props
        if not unique:
            dir_shortname = directory[ directory.rfind('/') + 1 : ][ : 30]
            if len(directory) > len(dir_shortname):
                dir_shortname += '...'
            unique = set(['dir='+dir_shortname, 'properties=all_common'])
        unique_props[directory] = unique

    return common_props, unique_props
