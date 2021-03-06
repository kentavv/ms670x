#!/usr/bin/python

# ms670x.py - Data decoder for Mastech MS670x Digital Sound Level Meters
#           - Tested with a Mastech MS6701 Digital Sound Level Meter
#
# Written July 2, 2016 by Kent A. Vander Velden <kent.vandervelden@gmail.com>
#
# To the extent possible under law, the author(s) have dedicated all copyright 
# and related and neighboring rights to this software to the public domain 
# worldwide. This software is distributed without any warranty.
#
# You should have received a copy of the CC0 Public Domain Dedication along 
# with this software. If not, see 
#                       <http://creativecommons.org/publicdomain/zero/1.0/>. 
#
#
# If you use this software, please consider contacting me. I'd like to hear
# about your work.


# Notes
#
# If the serial connection is enabled, and recording is later enabled and then
# disabled on the meter, the serial connection may only read every other 
# packet. Disable and and then re-enable the serial connection on the meter
# to restore functionality.
#
# If 'maximum' is enabled on the meter, the meter continues to transmit the 
# current reading. The maximum has to be calculated based on received data
#
# 'Low battery' warning appears when voltage is below 6.95V
# Current draw is typically 26mA when on and less than 0.1uA when off
#
# The '30-130' is actually an 'auto-range' range. The manual warns this mode
# is 'unfit for measuring a[n] instantaneous and impactive noises' (pg. 10)
#
# The over-under warning is sent from the meter, but could be constructed
# from the current range sent in live and pre-recorded measurements.
#
# The meter does not need to already be in RS232 mode to send pre-recorded data.
# Sending pre-recorded data will enable RS232 mode until complete if necessary,
# and will not leave the meter in RS232 mode if it was not already.
#

import serial
from datetime import datetime

ser = serial.Serial(port='/dev/ttyUSB0', baudrate=2400, bytesize=serial.EIGHTBITS, 
                    parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE, 
                    timeout=1.5, xonxoff=False, rtscts=False, dsrdtr=False)

ser.flushInput()
ser.flushOutput()

st = -1 # discard bytes until reading first start-end byte
measurement_range = 0
rc_f = ''

while True:
  # Read a single byte at a time until syncing with a start-end byte, then change 
  # state to read a message, and repeat.
  if st == 0 or st == -1:
    c = ser.read()
    if c == '':
      print 'unable to read from device'
      continue
    c = ord(c)

#>>> print '\n'.join(map(str, [bin(128), bin(128+6), bin(141), bin(144), bin(128+32), bin(128+6+32)]))
#0b10000000 128 pre-recorded
#0b10000110 134 pre-recorded
#0b10001101 141 ?????
#0b10010000 144 - end
#0b10100000 160 live
#0b10100110 166 live
# are there other start-end flags?
# bit 7 is the start-end flag
# bit 5 indicates live recording
# bit 4 indicates done reading pre-recorded measurements?

    if not ((c >> 7) & 1):
      continue

    if 128+32 <= c and c <= 134+32:
      st = 1
      rc_f = 'live'
      measurement_range = c
      measurement_range -= 32
    elif 128 <= c and c <= 134:
      st = 1
      rc_f = 'pre-recorded'
      measurement_range = c
    elif c == 144:
      print 'Done reading pre-recorded measurements'
    else:
      if st != -1:
        print 'Unknown start-end flag:', c
    if st == 1:
      measurement_range = {128:[30, 80],  129:[40, 90],  130:[50, 100], 
                           131:[60, 110], 132:[70, 120], 133:[80, 130], 
                           134:[30, 130]}[measurement_range]
  elif st == 1:
    dat = ser.read(size=17)
    if len(dat) != 17:
      print 'incomplete read from device'
      continue
    st = 0

    dat = map(ord, dat)
    #print dat
    #print '[A, B, B, B, B, Y, Y, M, M, D, D, C, C, C, C, C, C]'
    # [8, 0, 4, 8, 2, 1, 7, 0, 7, 7, 1, 1, 6, 0, 8, 5, 2]

    # dat[0].b6 = 0:battery fine, 1:low battery
    # dat[0].b5 = 0:max not enabled, 1:max enabled
    # dat[0].b4 = 0:record space available, 1:record space filled
    # dat[0].b3 = frequency weighting 1:A, 0:C
    # dat[0].b2 = time weighting: 0:fast(125ms), 1:slow(1s)
    # dat[0].b1 = under warning: 0:not under low end, 1:under low end
    # dat[0].b0 = over warning: 0:not over high end, 1:over high end
    # dat[1, 2, 3, 4] = db(frequency_weighting) 123.4
    # dat[5:6] = year (00-99)
    # dat[7:8] = month
    # dat[9:10] = day 42=2, 71=31
    # dat[11,12 : 13,14 : 15,16] = time HR:MN:SS

    # construct a warning if there are unknown bits set
    ob_warning = dat[0]
    ob_warning &= ~ 0b1111111
    if ob_warning:
      ob_warning = 'unknown bits:'+str(bin(ob_warning))
    else:
      ob_warning = ''

    low_battery = (dat[0] >> 6) & 1
    low_battery = {0:'', 1:'low_battery'}[low_battery]

    max_enabled = (dat[0] >> 5) & 1
    max_enabled = {0:'', 1:'max_enabled'}[max_enabled]

    full_warning = (dat[0] >> 4) & 1
    full_warning = {0:'', 1:'mem-full'}[full_warning]

    frequency_weighting = (dat[0] >> 3) & 1
    if rc_f == 'pre-recorded':
      # the meaning of frequency_weight flag appears to be inverted when reading pre-recorded data
      frequency_weighting = 1 - frequency_weighting
    frequency_weighting = {0:'C', 1:'A'}[frequency_weighting]

    time_weighting = (dat[0] >> 2) & 1
    time_weighting = {0:'fast(125ms)', 1:'slow(1s)'}[time_weighting]

    under_warning = (dat[0] >> 1) & 1
    under_warning = {0:'', 1:'under'}[under_warning]

    over_warning = (dat[0] >> 0) & 1
    over_warning = {0:'', 1:'over'}[over_warning]

    db = dat[1] * 100 + dat[2] * 10 + dat[3] * 1 + dat[4] * 0.1
    dat[9] -= 4 # why is the day offset by 40?
    dt = '20{0:d}{1:d}-{2:d}{3:d}-{4:d}{5:d}'.format(*dat[5:11])
    tm = '{0:d}{1:d}:{2:d}{3:d}:{4:d}{5:d}'.format(*dat[11:17])

    dt_tm = dt + ' ' + tm

    # enable if you want to do date-time validation or other calculations
    try:
      dt_tm = datetime.strptime(dt_tm, '%Y-%m-%d %H:%M:%S')
    except:
      print 'Could not convert date-time:', dt_tm
      continue

    ou_warning = under_warning + over_warning
 
    print rc_f, dt_tm, db, 'db'+frequency_weighting, time_weighting, \
          measurement_range, ou_warning, max_enabled, ob_warning, \
          full_warning, low_battery
 

# Sending pre-recorded data seems to have some problems...
#
# 1. The meaning of the frequency weighting flag is inverted, but that we correct
# in software.
#
# 2. It is possible for time points to repeat in recorded data, seems to occur when changing
# frequency weighting modes.
#
# pre-recorded 2016-07-03 19:01:12 51.7 dbA slow(1s) [40, 90]     
# pre-recorded 2016-07-03 19:01:13 51.8 dbA slow(1s) [40, 90]     
# pre-recorded 2016-07-03 19:01:14 51.8 dbA slow(1s) [40, 90]     <----
# pre-recorded 2016-07-03 19:01:15 51.8 dbA slow(1s) [40, 90]     
# pre-recorded 2016-07-03 19:01:16 51.7 dbA slow(1s) [40, 90]     
# pre-recorded 2016-07-03 19:01:17 51.7 dbA slow(1s) [40, 90]     
# pre-recorded 2016-07-03 19:01:18 51.7 dbA slow(1s) [40, 90]     
# pre-recorded 2016-07-03 19:01:19 51.7 dbA slow(1s) [40, 90]     
# pre-recorded 2016-07-03 19:01:20 51.6 dbA slow(1s) [40, 90]     
# pre-recorded 2016-07-03 19:01:21 51.7 dbA slow(1s) [40, 90]     <----
# pre-recorded 2016-07-03 19:01:14 55.1 dbC slow(1s) [40, 90]     <---- being repeating
# pre-recorded 2016-07-03 19:01:15 57.5 dbC slow(1s) [40, 90]     
# pre-recorded 2016-07-03 19:01:16 58.3 dbC slow(1s) [40, 90]     
# pre-recorded 2016-07-03 19:01:17 58.8 dbC slow(1s) [40, 90]     
# pre-recorded 2016-07-03 19:01:18 58.5 dbC slow(1s) [40, 90]     
# pre-recorded 2016-07-03 19:01:19 58.3 dbC slow(1s) [40, 90] 
# pre-recorded 2016-07-03 19:01:20 58.3 dbC slow(1s) [40, 90]
# pre-recorded 2016-07-03 19:01:21 58.6 dbC slow(1s) [40, 90]     <---- end repeating
# pre-recorded 2016-07-03 19:01:22 59.0 dbC slow(1s) [40, 90]     
# pre-recorded 2016-07-03 19:01:23 58.5 dbC slow(1s) [40, 90]     
#
# 3. Sometimes the pre-recorded data can have a future timestamp.
#  
# pre-recorded 2016-07-03 19:12:02 56.5 dbA slow(1s) [40, 90]     
# pre-recorded 2016-07-03 19:12:03 56.3 dbA slow(1s) [40, 90]     
# pre-recorded 2016-07-03 19:12:04 56.2 dbA slow(1s) [40, 90]     
# pre-recorded 2016-07-03 19:12:05 55.8 dbA slow(1s) [40, 90]     
# pre-recorded 2016-07-03 19:12:06 55.4 dbA slow(1s) [40, 90]     <---- future timestamp
# pre-recorded 2016-07-03 19:06:53 60.6 dbC slow(1s) [40, 90]     
# ....
# pre-recorded 2016-07-03 19:07:03 53.1 dbA slow(1s) [40, 90]     <---- timestamp from near when send was pressed
# Done reading pre-recorded measurements
# live 2016-07-03 19:08:02 53.2 dbA slow(1s) [40, 90]     <---- timestamp now
#
#
# Some of these and others, such as the day being offset by 40, were verified
# to be a problem with the Mastech software as well. Below is a sample report
# from the Mastech software. Unfortunately, it does not save fully decoded
# packets, so yet another reason to write ones own software.
#
#
#
#Sound Level Meter Data Report   (07/03/2016/19:19:11/422)               
#                
#Record  Date    Time    Range   Value (dB)
#...
#310 16-07-43    19:16:03    40-90   60
#311 16-07-43    19:16:04    40-90   59.4
#312 16-07-43    19:16:05    40-90   58.8        <----
#313 16-07-43    19:16:06    40-90   60
#314 16-07-43    19:16:07    40-90   59.3
#315 16-07-43    19:16:08    40-90   59.4
#316 16-07-43    19:16:09    40-90   59.9
#317 16-07-43    19:16:10    40-90   60.1        <---- 
#318 16-07-43    19:16:05    40-90   59.6        <---- repeats begin
#319 16-07-43    19:16:06    40-90   57.9
#320 16-07-43    19:16:07    40-90   56.7
#321 16-07-43    19:16:08    40-90   56.4
#322 16-07-43    19:16:09    40-90   56          <---- repeats end
#323 16-07-43    19:16:10    40-90   55.5
#324 16-07-43    19:16:11    40-90   55.5
#325 16-07-43    19:16:12    40-90   55.5
#
