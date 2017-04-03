"""
Definition of :class:`Lightcurve`.

:class:`Lightcurve` is used to create light curves out of photon counting data
or to save existing light curves in a class that's easy to use.
"""
import logging
import numpy as np
import stingray.io as io
import stingray.utils as utils
from stingray.exceptions import StingrayError
from stingray.utils import simon, assign_value_if_none
from stingray.gti import cross_two_gtis, join_gtis, gti_border_bins
from stingray.gti import check_gtis

__all__ = ["Lightcurve"]


class Lightcurve(object):
    def __init__(self, time, counts, input_counts=True, gti=None):
        """
        Make a light curve object from an array of time stamps and an
        array of counts.

        Parameters
        ----------
        time: iterable
            A list or array of time stamps for a light curve

        counts: iterable, optional, default None
            A list or array of the counts in each bin corresponding to the
            bins defined in `time` (note: **not** the count rate, i.e.
            counts/second, but the counts/bin).

        input_counts: bool, optional, default True
            If True, the code assumes that the input data in 'counts'
            is in units of counts/bin. If False, it assumes the data
            in 'counts' is in counts/second.

        gti: 2-d float array, default None
            [[gti0_0, gti0_1], [gti1_0, gti1_1], ...]
            Good Time Intervals. They are *not* applied to the data by default.
            They will be used by other methods to have an indication of the
            "safe" time intervals to use during analysis.

        Attributes
        ----------
        time: numpy.ndarray
            The array of midpoints of time bins.

        bin_lo:
            The array of lower time stamp of time bins.

        bin_hi:
            The array of higher time stamp of time bins.

        counts: numpy.ndarray
            The counts per bin corresponding to the bins in `time`.

        countrate: numpy.ndarray
            The counts per second in each of the bins defined in `time`.

        meanrate: float
            The mean count rate of the light curve.
            
        meancounts: float
            The mean counts of the light curve.

        n: int
            The number of data points in the light curve.

        dt: float
            The time resolution of the light curve.

        tseg: float
            The total duration of the light curve.

        tstart: float
            The start time of the light curve.

        gti: 2-d float array
            [[gti0_0, gti0_1], [gti1_0, gti1_1], ...]
            Good Time Intervals. They indicate the "safe" time intervals
            to be used during the analysis of the light curve.

        """
        if not np.all(np.isfinite(time)):
            raise ValueError("There are inf or NaN values in "
                             "your time array!")

        if not np.all(np.isfinite(counts)):
            raise ValueError("There are inf or NaN values in "
                             "your counts array!")

        if len(time) != len(counts):

            raise StingrayError("time and counts array are not "
                                "of the same length!")

        if len(time) <= 1:
            raise StingrayError("A single or no data points can not create "
                                "a lightcurve!")

        self.time = np.asarray(time)
        self.dt = time[1] - time[0]

        self.bin_lo = self.time - 0.5 * self.dt
        self.bin_hi = self.time + 0.5 * self.dt

        if input_counts:
            self.counts = np.asarray(counts)
            self.countrate = self.counts / self.dt
        else:
            self.countrate = np.asarray(counts)
            self.counts = self.countrate * self.dt

        self.meanrate = np.mean(self.countrate)
        self.meancounts = np.mean(self.counts)
        self.n = self.counts.shape[0]

        # Issue a warning if the input time iterable isn't regularly spaced,
        # i.e. the bin sizes aren't equal throughout.
        dt_array = np.diff(self.time)
        if not (np.allclose(dt_array, np.repeat(self.dt, dt_array.shape[0]))):
            simon("Bin sizes in input time array aren't equal throughout! "
                  "This could cause problems with Fourier transforms. "
                  "Please make the input time evenly sampled.")

        self.tseg = self.time[-1] - self.time[0] + self.dt
        self.tstart = self.time[0] - 0.5*self.dt
        self.gti = \
            np.asarray(assign_value_if_none(gti,
                                            [[self.tstart,
                                              self.tstart + self.tseg]]))
        check_gtis(self.gti)

    def shift(self, time_shift):
        """
        Shift the light curve and the GTIs in time.

        Parameters
        ----------
        time_shift: float
            The amount of time that the light curve will be shifted
        """
        new_lc = Lightcurve(self.time + time_shift, self.counts,
                            gti=self.gti + time_shift)
        new_lc.countrate = self.countrate
        new_lc.counts = self.counts
        new_lc.meanrate = np.mean(new_lc.countrate)
        new_lc.meancounts = np.mean(new_lc.counts)
        return new_lc

    def __add__(self, other):
        """
        Add two light curves element by element having the same time array.

        This magic method adds two Lightcurve objects having the same time
        array such that the corresponding counts arrays get summed up.

        GTIs are crossed, so that only common intervals are saved.

        Example
        -------
        >>> time = [5, 10, 15]
        >>> count1 = [300, 100, 400]
        >>> count2 = [600, 1200, 800]
        >>> gti1 = [[0, 20]]
        >>> gti2 = [[0, 25]]
        >>> lc1 = Lightcurve(time, count1, gti=gti1)
        >>> lc2 = Lightcurve(time, count2, gti=gti2)
        >>> lc = lc1 + lc2
        >>> lc.counts
        array([ 900, 1300, 1200])
        """

        # ValueError is raised by Numpy while asserting np.equal over arrays
        # with different dimensions.
        try:
            assert np.all(np.equal(self.time, other.time))
        except (ValueError, AssertionError):
            raise ValueError("Time arrays of both light curves must be "
                             "of same dimension and equal.")

        new_counts = np.add(self.counts, other.counts)
        common_gti = cross_two_gtis(self.gti, other.gti)

        lc_new = Lightcurve(self.time, new_counts, gti=common_gti)

        return lc_new

    def __sub__(self, other):
        """
        Subtract two light curves element by element having the same time array.

        This magic method subtracts two Lightcurve objects having the same
        time array such that the corresponding counts arrays interferes with
        each other.

        GTIs are crossed, so that only common intervals are saved.

        Example
        -------
        >>> time = [10, 20, 30]
        >>> count1 = [600, 1200, 800]
        >>> count2 = [300, 100, 400]
        >>> gti1 = [[0, 20]]
        >>> gti2 = [[0, 25]]
        >>> lc1 = Lightcurve(time, count1, gti=gti1)
        >>> lc2 = Lightcurve(time, count2, gti=gti2)
        >>> lc = lc1 - lc2
        >>> lc.counts
        array([ 300, 1100,  400])
        """

        # ValueError is raised by Numpy while asserting np.equal over arrays
        # with different dimensions.
        try:
            assert np.all(np.equal(self.time, other.time))
        except (ValueError, AssertionError):
            raise ValueError("Time arrays of both light curves must be "
                             "of same dimension and equal.")

        new_counts = np.subtract(self.counts, other.counts)
        common_gti = cross_two_gtis(self.gti, other.gti)

        lc_new = Lightcurve(self.time, new_counts, gti=common_gti)

        return lc_new

    def __neg__(self):
        """
        Implement the behavior of negation of the light curve objects.

        The negation operator ``-`` is supposed to invert the sign of the count
        values of a light curve object.

        Example
        -------
        >>> time = [1, 2, 3]
        >>> count1 = [100, 200, 300]
        >>> count2 = [200, 300, 400]
        >>> lc1 = Lightcurve(time, count1)
        >>> lc2 = Lightcurve(time, count2)
        >>> lc_new = -lc1 + lc2
        >>> lc_new.counts
        array([100, 100, 100])
        """
        lc_new = Lightcurve(self.time, -1*self.counts, gti=self.gti)

        return lc_new

    def __len__(self):
        """
        Return the length of the data array of a light curve.

        This method implements overrides the len function over a Lightcurve
        object and returns the length of the time and count arrays.

        Example
        -------
        >>> time = [1, 2, 3]
        >>> count = [100, 200, 300]
        >>> lc = Lightcurve(time, count)
        >>> len(lc)
        3
        """
        return self.n

    def __getitem__(self, index):
        """
        Return the corresponding count value at the index or a new Lightcurve
        object upon slicing.

        This method adds functionality to retrieve the count value at
        a particular index. This also can be used for slicing and generating
        a new Lightcurve object.

        Parameters
        ----------
        index : int or slice instance
            Index value of the time array or a slice object.

        Example
        -------
        >>> time = [1, 2, 3, 4, 5, 6, 7, 8, 9]
        >>> count = [11, 22, 33, 44, 55, 66, 77, 88, 99]
        >>> lc = Lightcurve(time, count)
        >>> lc[2]
        33
        >>> lc[:2].counts
        array([11, 22])
        """
        if isinstance(index, int):
            return self.counts[index]
        elif isinstance(index, slice):
            new_counts = self.counts[index.start:index.stop:index.step]
            new_time = self.time[index.start:index.stop:index.step]
            return Lightcurve(new_time, new_counts)
        else:
            raise IndexError("The index must be either an integer or a slice "
                             "object !")

    @staticmethod
    def make_lightcurve(toa, dt, tseg=None, tstart=None, gti=None):

        """
        Make a light curve out of photon arrival times.

        Parameters
        ----------
        toa: iterable
            list of photon arrival times

        dt: float
            time resolution of the light curve (the bin width)

        tseg: float, optional, default None
            The total duration of the light curve.
            If this is `None`, then the total duration of the light curve will
            be the interval between the arrival between the first and the last
            photon in `toa`.

                **Note**: If tseg is not divisible by dt (i.e. if tseg/dt is
                not an integer number), then the last fractional bin will be
                dropped!

        tstart: float, optional, default None
            The start time of the light curve.
            If this is None, the arrival time of the first photon will be used
            as the start time of the light curve.

        gti: 2-d float array
            [[gti0_0, gti0_1], [gti1_0, gti1_1], ...]
            Good Time Intervals

        Returns
        -------
        lc: :class:`Lightcurve` object
            A light curve object with the binned light curve

        """

        # tstart is an optional parameter to set a starting time for
        # the light curve in case this does not coincide with the first photon
        if tstart is None:
            # if tstart is not set, assume light curve starts with first photon
            tstart = toa[0]

        # compute the number of bins in the light curve
        # for cases where tseg/dt is not integer. 
        # TODO: check that this is always consistent and that we 
        # are not throwing away good events.

        if tseg is None:
            tseg = toa[-1] - toa[0]

        logging.info("make_lightcurve: tseg: " + str(tseg))

        timebin = np.int(tseg/dt)
        logging.info("make_lightcurve: timebin:  " + str(timebin))

        tend = tstart + timebin*dt

        counts, histbins = np.histogram(toa, bins=timebin,
                                        range=[tstart, tend])

        dt = histbins[1] - histbins[0]

        time = histbins[:-1] + 0.5*dt

        counts = np.asarray(counts)

        return Lightcurve(time, counts, gti=gti)

    def rebin(self, dt_new, method='sum'):
        """
        Rebin the light curve to a new time resolution. While the new
        resolution need not be an integer multiple of the previous time
        resolution, be aware that if it is not, the last bin will be cut
        off by the fraction left over by the integer division.

        Parameters
        ----------
        dt_new: float
            The new time resolution of the light curve. Must be larger than
            the time resolution of the old light curve!

        method: {"sum" | "mean" | "average"}, optional, default "sum"
            This keyword argument sets whether the counts in the new bins
            should be summed or averaged.


        Returns
        -------
        lc_new: :class:`Lightcurve` object
            The :class:`Lightcurve` object with the new, binned light curve.
        """

        if dt_new < self.dt:
            raise ValueError("New time resolution must be larger than "
                             "old time resolution!")

        bin_time, bin_counts, _ = utils.rebin_data(self.time,
                                                   self.counts,
                                                   dt_new, method)

        lc_new = Lightcurve(bin_time, bin_counts)
        return lc_new

    def join(self, other):
        """
        Join two lightcurves into a single object.

        The new Lightcurve object will contain time stamps from both the
        objects. The count per bin in the resulting object will be the
        individual count per bin, or the average in case of overlapping
        time arrays of both lightcurve objects.

        Good Time intervals are also joined.

        Note : Time array of both lightcurves should not overlap each other.

        Parameters
        ----------
        other : Lightcurve object
            The other Lightcurve object which is supposed to be joined with.

        Returns
        -------
        lc_new : Lightcurve object
            The resulting lightcurve object.

        Example
        -------
        >>> time1 = [5, 10, 15]
        >>> count1 = [300, 100, 400]
        >>> time2 = [20, 25, 30]
        >>> count2 = [600, 1200, 800]
        >>> lc1 = Lightcurve(time1, count1)
        >>> lc2 = Lightcurve(time2, count2)
        >>> lc = lc1.join(lc2)
        >>> lc.time
        array([ 5, 10, 15, 20, 25, 30])
        >>> lc.counts
        array([ 300,  100,  400,  600, 1200,  800])
        """
        if self.dt != other.dt:
            utils.simon("The two light curves have different bin widths.")

        if self.tstart <= other.tstart:
            new_time = np.unique(np.concatenate([self.time, other.time]))
        else:
            new_time = np.unique(np.concatenate([other.time, self.time]))

        if len(new_time) != len(self.time) + len(other.time):
            utils.simon("The two light curves have overlapping time ranges. "
                        "In the common time range, the resulting count will "
                        "be the average of the counts in the two light "
                        "curves. If you wish to sum, use `lc_sum = lc1 + "
                        "lc2`.")

        new_counts = []

        # For every time stamp, get the individual time counts and add them.
        for time in new_time:
            try:
                count1 = self.counts[np.where(self.time == time)[0][0]]
            except IndexError:
                count1 = None

            try:
                count2 = other.counts[np.where(other.time == time)[0][0]]
            except IndexError:
                count2 = None

            if count1 is not None:
                if count2 is not None:
                    # Average the overlapping counts
                    new_counts.append((count1 + count2) / 2)
                else:
                    new_counts.append(count1)
            else:
                new_counts.append(count2)

        new_counts = np.asarray(new_counts)

        gti = join_gtis(self.gti, other.gti)

        lc_new = Lightcurve(new_time, new_counts, gti=gti)

        return lc_new

    def truncate(self, start=0, stop=None, method="index"):
        """
        Truncate a Lightcurve object from points on the time array.

        This method allows the truncation of a Lightcurve object and returns
        a new light curve.

        Parameters
        ----------
        start : int, default 0
            Index of the starting point of the truncation.

        stop : int, default None
            Index of the ending point (exclusive) of the truncation. If no
            value of stop is set, then points including the last point in
            the counts array are taken in count.

        method : {"index" | "time"}, optional, default "index"
            Type of the start and stop values. If set to "index" then
            the values are treated as indices of the counts array, or
            if set to "time", the values are treated as actual time values.

        Example
        -------
        >>> time = [1, 2, 3, 4, 5, 6, 7, 8, 9]
        >>> count = [10, 20, 30, 40, 50, 60, 70, 80, 90]
        >>> lc = Lightcurve(time, count)
        >>> lc_new = lc.truncate(start=2, stop=8)
        >>> lc_new.counts
        array([30, 40, 50, 60, 70, 80])
        >>> lc_new.time
        array([3, 4, 5, 6, 7, 8])

        # Truncation can also be done by time values
        >>> lc_new = lc.truncate(start=6, method='time')
        >>> lc_new.time
        array([6, 7, 8, 9])
        >>> lc_new.counts
        array([60, 70, 80, 90])

        Returns
        -------
        lc_new: :class:`Lightcurve` object
            The :class:`Lightcurve` object with truncated time and counts
            arrays.
        """

        if not isinstance(method, str):
            raise TypeError("method key word argument is not "
                            "a string !")

        if method.lower() not in ['index', 'time']:
            raise ValueError("Unknown method type " + method + ".")

        if method.lower() == 'index':
            return self._truncate_by_index(start, stop)
        else:
            return self._truncate_by_time(start, stop)

    def _truncate_by_index(self, start, stop):
        """Private method for truncation using index values."""
        time_new = self.time[start:stop]
        counts_new = self.counts[start:stop]
        gti = \
            cross_two_gtis(self.gti,
                           np.asarray([[self.time[start] - 0.5 * self.dt,
                                        time_new[-1] + 0.5 * self.dt]]))

        return Lightcurve(time_new, counts_new, gti=gti)

    def _truncate_by_time(self, start, stop):
        """Private method for truncation using time values."""

        if stop is not None:
            if start > stop:
                raise ValueError("start time must be less than stop time!")

        if not start == 0:
            start = np.where(self.time == start)[0][0]

        if stop is not None:
            stop = np.where(self.time == stop)[0][0]

        return self._truncate_by_index(start, stop)

    def sort(self, reverse=False):
        """
        Sort a Lightcurve object in accordance with its counts array.

        A Lightcurve can be sorted in either increasing or decreasing order
        using this method. The counts array gets sorted and the time array is
        changed accordingly.

        Parameters
        ----------
        reverse : boolean, default False
            If True then the object is sorted in reverse order.

        Example
        -------
        >>> time = [1, 2, 3]
        >>> count = [200, 100, 300]
        >>> lc = Lightcurve(time, count)
        >>> lc.sort()
        >>> lc.counts
        array([100, 200, 300])
        >>> lc.time
        array([2, 1, 3])

        Returns
        -------
        lc_new: :class:`Lightcurve` object
            The :class:`Lightcurve` object with truncated time and counts
            arrays.
        """
        new_counts = sorted(self.counts, reverse=reverse)
        new_time = []
        for count in np.unique(new_counts):
            for index in np.where(self.counts == count)[0]:
                new_time.append(self.time[index])

        if reverse:
            new_time.reverse()

        self.time = np.asarray(new_time)
        self.counts = np.asarray(new_counts)

    def plot(self, labels=None, axis=None, title=None, marker='-', save=False,
             show=False, filename=None):
        """
        Plot the Lightcurve using Matplotlib.

        Plot the Lightcurve object on a graph ``self.time`` on x-axis and
        ``self.counts`` on y-axis.

        Parameters
        ----------
        labels : iterable, default None
            A list of tuple with xlabel and ylabel as strings.

        axis : list, tuple, string, default None
            Parameter to set axis properties of Matplotlib figure. For example
            it can be a list like ``[xmin, xmax, ymin, ymax]`` or any other
            acceptable argument for `matplotlib.pyplot.axis()` function.

        title : str, default None
            The title of the plot.

        marker : str, default '-'
            Line style and color of the plot. Line styles and colors are
            combined in a single format string, as in ``'bo'`` for blue
            circles. See `matplotlib.pyplot.plot` for more options.

        save : boolean, optional (default=False)
            If True, save the figure with specified filename.

        filename : str
            File name of the image to save. Depends on the boolean ``save``.
        """
        try:
            import matplotlib.pyplot as plt
        except ImportError:
            raise ImportError("Matplotlib required for plot()")

        fig = plt.figure()
        fig = plt.plot(self.time, self.counts, marker)

        if labels is not None:
            try:
                plt.xlabel(labels[0])
                plt.ylabel(labels[1])
            except TypeError:
                utils.simon("``labels`` must be either a list or tuple with "
                            "x and y labels.")
                raise
            except IndexError:
                utils.simon("``labels`` must have two labels for x and y "
                            "axes.")
                # Not raising here because in case of len(labels)==1, only
                # x-axis will be labelled.

        if axis is not None:
            plt.axis(axis)

        if title is not None:
            plt.title(title)

        if save:
            if filename is None:
                plt.savefig('out.png')
            else:
                plt.savefig(filename)

    def write(self, filename, format_='pickle', **kwargs):
        """
        Exports LightCurve object.

        Parameters
        ----------
        filename: str
            Name of the LightCurve object to be created.

        format\_: str
            Available options are 'pickle', 'hdf5', 'ascii'
        """

        if format_ == 'ascii':
            io.write(np.array([self.time, self.counts]).T,
                     filename, format_, fmt=["%s", "%s"])

        elif format_ == 'pickle':
            io.write(self, filename, format_)

        elif format_ == 'hdf5':
            io.write(self, filename, format_)

        else:
            utils.simon("Format not understood.")

    def read(self, filename, format_='pickle'):
        """
        Imports LightCurve object.

        Parameters
        ----------
        filename: str
            Name of the LightCurve object to be read.

        format\_: str
            Available options are 'pickle', 'hdf5', 'ascii'

        Returns
        --------
        If format\_ is 'ascii': astropy.table is returned.
        If format\_ is 'hdf5': dictionary with key-value pairs is returned.
        If format\_ is 'pickle': class object is set.
        """

        if format_ == 'ascii':
            data = io.read(filename, format_)
            return Lightcurve(np.asarray(data['col1']), np.asarray(data['col2']))
        elif format_ == 'hdf5':
            data = io.read(filename, format_)
            return Lightcurve(data['time'], data['counts'])

        elif format_ == 'pickle':
            return io.read(filename, format_)

        else:
            utils.simon("Format not understood.")

    def split_by_gti(self):
        """
        Splits the `LightCurve` into a list of `LightCurve`s , using GTIs.
        """
        list_of_lcs = []

        start_bins, stop_bins = gti_border_bins(self.gti, self.time)
        for i in range(len(start_bins)):
            start = start_bins[i]
            stop = stop_bins[i]
            # Note: GTIs are consistent with default in this case!
            new_lc = Lightcurve(self.time[start:stop], self.counts[start:stop])
            list_of_lcs.append(new_lc)

        return list_of_lcs
