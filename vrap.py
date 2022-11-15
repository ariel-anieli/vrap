import functools
import logging
import os
import re
import subprocess
import sys
import tarfile
import xml.etree.ElementTree as ET

logging.basicConfig(stream=sys.stdout, format='%(message)s', level=logging.INFO)

run_cmd = lambda cmd: subprocess.run(
    cmd.split(),
    text   = True,
    check  = True,
    stdout = subprocess.PIPE,
    stderr = subprocess.STDOUT
).stdout

def fold_if_true_and_apply(args, *funcs):
    return functools.reduce(
        lambda _in, func: func(_in),
        funcs,
        args)

def no_tx_errors(logs):
    return len([line for line in logs
                if re.search('Unsuccess.*: [^0]', line)])==0 \
            and len([line for line in logs
                     if re.search('Attempt', line)])>0

def stop_if_cond_is_true(logs=['1'], cond=lambda x: x):
    if cond(logs):
        return 'Done'
    else:
        # set_ramp_up_height()
        # logging.info(get_ramp_up_height())

        fold_if_true_and_apply(
            'config.tcl',
            get_archive_name,
            uncompress_archive_and_get_dir,
            retrieve_load_profiles,
            edit_load_profile,
            rebuild_archive,
        )

        return stop_if_cond_is_true(run_cmd('cat obs.log').split(), cond) # tclsh.exe test.tcl'

def get_raw_loadnames(entries):
    return {'entries' : entries,
            'ldnames' : [entry for entry in entries
                         if re.search('loads', entry)]}

def get_raw_heights(args):
    return {
        'heights' : [entry for entry in args['entries']
                     if re.search('step.2..height', entry)],
        'ldnames' : args['ldnames']}

def clean_loadnames_and_height_values(args):
    clean_ldnames = [re.search('(?<=loads )\w+', entry).group(0)
                     for entry in args['ldnames']
                     if re.search('(?<=loads )\w+', entry)]
    clean_heightv = [re.search('(?<=height..)\w+', entry).group(0)
                     for entry in args['heights']
                     if re.search('(?<=height..)\w+', entry)]

    return {ldname : int(height)
            for ldname in clean_ldnames
            for height in clean_heightv}

def get_ramp_up_height():
    with open('config.tcl') as cfg:
        config = cfg.readlines()

    return fold_if_true_and_apply(
        config,
        get_raw_loadnames,
        get_raw_heights,
        clean_loadnames_and_height_values,
    )

def edit_heights(config, ld_and_height):
    return config

def update_entry_or_pass(entry):
    m = re.search('(?<=height..)\w+', entry)

    if m:
        return re.sub('(?<=height .)\d+', str(int(2*int(m.group(0)))), entry)
    else:
        return entry

def set_ramp_up_height():
    with open('config.tcl', 'r') as file:
        config = fold_if_true_and_apply(
            file.readlines(),
            lambda _: [update_entry_or_pass(entry) for entry in _],
        )

    with open('config.tcl', 'w') as file:
        [file.write(entry) for entry in config]

def get_archive_name(config):
    with open(config, 'r') as file:
        return fold_if_true_and_apply(
            file.readlines(),
            lambda lines: [line for line in lines if re.search('\.spf', line)].pop(0),
            lambda line: re.search('(?<=\s\{).*\.spf', line).group(0),
        )

def uncompress_archive_and_get_dir(arch_name):
    with tarfile.open(arch_name) as arch:
        def is_within_directory(directory, target):
            
            abs_directory = os.path.abspath(directory)
            abs_target = os.path.abspath(target)
        
            prefix = os.path.commonprefix([abs_directory, abs_target])
            
            return prefix == abs_directory
        
        def safe_extract(tar, path=".", members=None, *, numeric_owner=False):
        
            for member in tar.getmembers():
                member_path = os.path.join(path, member.name)
                if not is_within_directory(path, member_path):
                    raise Exception("Attempted Path Traversal in Tar File")
        
            tar.extractall(path, members, numeric_owner=numeric_owner) 
            
        
        safe_extract(arch)
        
    return [name for name in os.listdir('tmp/AvExport') if name!='sapee'].pop(0)

def retrieve_load_profiles(ld_profile_folder):
    return {'load_profiles' : os.listdir('/'.join(['tmp/AvExport',
                                                   ld_profile_folder,
                                                   'loadprofiles'])),
            'load_dir'      : ld_profile_folder,
            'load_path'     : '/'.join(['tmp/AvExport',
                                        ld_profile_folder,
                                        'loadprofiles'])}

def edit_heights(args, profile):
    tree = ET.parse('/'.join([args['load_path'], profile]))

    for height in tree.findall(".//Step[Label='Ramp Up']/Height"):
        height.text = str(int(2*int(height.text)))
        dbg         = re.sub('\.xml', '', ','.join([profile, height.text]))
        logging.info(dbg)

    tree.write('/'.join([args['load_path'], profile]))

    return args

def edit_load_profile(args):
    return [edit_heights(args, profile) for profile in args['load_profiles']].pop(0)

def rebuild_archive(args):
    arch_name = get_archive_name('config.tcl')
    os.remove(arch_name)

    with tarfile.open(arch_name,
                      mode='x:gz',
                      format=tarfile.GNU_FORMAT) as arch:
        arch.add('tmp')

if __name__=="__main__":
    logging.info(stop_if_cond_is_true(cond=no_tx_errors))

