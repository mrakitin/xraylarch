#!/usr/bin/env python
"""
support for netcdf XRD files from **DETECTOR NAME**
in Epics Mapping Mode -- copied from xmap_netcdf.py (larch plugins)
mkak 2016.07.06
"""
import numpy as np
import os

import copy
from copy import deepcopy

import time

## Package for reading netcdf files (in scipy)
try:
    import scipy.io.netcdf
    netcdf_open = scipy.io.netcdf.netcdf_file
except ImportError:
    raise ImportError('cannot find scipy netcdf module')

def read_xrd_netcdf(fname,verbose=False): #npixels=self.nrows_expected
    ## Reads a netCDF file created for XRD mapping
    
#     a = time.time()
#     if verbose:
#         print(' reading %s' % fname)
#     
#     ## Reads an XRD netCDF file with the netCDF plugin buffers
#     xrd_file = netcdf_open(fname,'r')
#     xrd_data = xrd_file.variables['array_data'].data.copy()
# #     xrd_data = xrd_data.astype('uint16')
#     try:
#         xrd_file.close()
#     except:
#        pass
# #     
# #     ## Forces data into 3D shape
# #     shape = xrd_data.shape ## (no_images,pixels_x,pixels_y)
# #     if len(shape) == 2:
# #         print('Reshaping to (%i, %i, %i)' % (1, shape[0], shape[1]))
# #         xrd_data.shape = (1, shape[0], shape[1])
# # 
#     print '1',time.time()-a
#     return xrd_data

    a = time.time()
    if verbose:
        print(' reading %s' % fname)
    
    ## Reads an XRD netCDF file with the netCDF plugin buffers
    xrd_data = read_netcdf(fname,only_key='array_data').data
    xrd_data = xrd_data.astype('uint16')

    ## Forces data into 3D shape
    shape = xrd_data.shape ## (no_images,pixels_x,pixels_y)
    if len(shape) == 2:
        print('Reshaping to (%i, %i, %i)' % (1, shape[0], shape[1]))
        xrd_data.shape = (1, shape[0], shape[1])

    print '1',time.time()-a
    return xrd_data



def read_xrd_netcdf2(fname,verbose=False): #npixels=self.nrows_expected
    ## Reads a netCDF file created for XRD mapping
    
    a = time.time()
    if verbose:
        print(' reading %s' % fname)
    
    ## Reads an XRD netCDF file with the netCDF plugin buffers
    xrd_file = netcdf_open(fname,'r')
    xrd_data = xrd_file.variables['array_data'].data ##.copy()
#     xrd_data = xrd_data.astype('uint16')
    try:
        xrd_file.close()
    except:
       pass
#     
#     ## Forces data into 3D shape
#     shape = xrd_data.shape ## (no_images,pixels_x,pixels_y)
#     if len(shape) == 2:
#         print('Reshaping to (%i, %i, %i)' % (1, shape[0], shape[1]))
#         xrd_data.shape = (1, shape[0], shape[1])

    print '2',time.time()-a
    return xrd_data


def read_xrd_netcdf3(fname,verbose=False): #npixels=self.nrows_expected
    ## Reads a netCDF file created for XRD mapping
    
    a = time.time()
    if verbose:
        print(' reading %s' % fname)
    
    ## Reads an XRD netCDF file with the netCDF plugin buffers
    xrd_file = netcdf_open(fname,'r')
    xrd_data = xrd_file.variables['array_data'] ##.data ##.copy()
#     xrd_data = xrd_data.astype('uint16')
    try:
        xrd_file.close()
    except:
       pass
#     
#     ## Forces data into 3D shape
#     shape = xrd_data.shape ## (no_images,pixels_x,pixels_y)
#     if len(shape) == 2:
#         print('Reshaping to (%i, %i, %i)' % (1, shape[0], shape[1]))
#         xrd_data.shape = (1, shape[0], shape[1])

    print '3',time.time()-a
    return xrd_data

def read_xrd_netcdf4(fname,verbose=False): #npixels=self.nrows_expected
    ## Reads a netCDF file created for XRD mapping
    
    a = time.time()
    if verbose:
        print(' reading %s' % fname)
    

    xrd_data = read_xrd_netcdf3(fname).data

    print '4',time.time()-a
    return xrd_data


# def read_xrd_netcdf(fname,verbose=False): 
#     ## Reads a netCDF file created for XRD mapping
#     
#     if verbose:
#         print(' reading %s' % fname)
#     
#     ## Reads an XRD netCDF file with the netCDF plugin buffers
#     xrd_data = read_netcdf(fname,only_key='array_data')
#     
#     xrd_data = xrd_data.astype('uint16')
# 
#     
#     ## Forces data into 3D shape
#     shape = xrd_data.shape ## (no_images,pixels_x,pixels_y)
#     if len(shape) == 2:
#         print('Reshaping to (%i, %i, %i)' % (1, shape[0], shape[1]))
#         xrd_data.shape = (1, shape[0], shape[1])
# 
#     return xrd_data
#     
# def read_xrd_netcdf_exptime(fname,verbose=False):
#     '''
#     returns header information for provided xrd netcdf file
#     '''
#     
#     return read_netcdf(fname,only_key='Attr_FrameTime')
# 
def read_netcdf(fname,verbose=False,only_key=None):
    '''
    returns dictionary of all information in provided xrd netcdf file
    '''
   
    file_netcdf = netcdf_open(fname)

    if only_key is not None and only_key is not in file_netcdf.variables.keys():
        return file_netcdf.variables[only_key]
    else:
        netcdf_dict = {}
        for key,val in dict(file_netcdf.variables).iteritems():
            netcdf_dict[key] = val


        return netcdf_dict



def test_read(fname):
    print( fname,  os.stat(fname))
    fd = read_xrd_netcdf(fname, verbose=True)
    print(fd.counts.shape)

def registerLarchPlugin():
    return ('_xrd', {'read_xrd_netcdf': read_xrd_netcdf})
