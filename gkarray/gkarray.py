import numpy as np


class UnequalEpsilonException(Exception):
    pass


class Entry:
    
    def __init__(self, val, g, delta):
        self.val = val
        self.g = g
        self.delta = delta

    def __repr__(self):
        return 'Entry(val={}, g={}, delta={})'.format(self.val, self.g, self.delta)


class GKArray:

    def __init__(self, eps):
        self.eps = eps
        self.entries = []
        self.incoming = []
        self._min = float('+inf')
        self._max = float('-inf')
        self._n = 0
        self._sum = 0
        self._avg = 0

    @property
    def name(self):
        return 'GKArray'

    def num_values(self):
        return self._n

    def avg(self):
        return self._avg

    def sum(self):
        return self._sum

    def size(self):
        if len(self.incoming) > 0:
            self.merge_compress()
        return len(self.entries)

    def add(self, val):
        """ Add a value to the sketch.
        """
        self._n += 1
        self._sum += val
        self._avg += (val - self._avg)*(1.0/self._n)
        self.incoming.append(val)
        if val < self._min:
            self._min = val
        if val > self._max:
            self._max = val
        if self._n % (int(1.0/self.eps) + 1) == 0:
            self.merge_compress()

    def merge_compress(self, entries=[]):
        """ Merge the given entry list into self.entries as well as compressing any values in
        self.incoming buffer.

        Parameters:
            entries: list of Entry 
        """
        removal_threshold = np.floor(2.0*self.eps*(self._n - 1))
        incoming = self.incoming + [Entry(e.val, e.g, e.delta) for e in entries]  
        incoming = sorted(incoming, key=lambda x: x.val)

        merged = []
        i, j = 0, 0
        while i < len(incoming) or j < len(self.entries):
            if i == len(incoming):
                # done with incoming; now only considering entries 
                if j + 1 < len(self.entries) and\
                   self.entries[j].g + self.entries[j+1].g + self.entries[j+1].delta <= removal_threshold:
                    self.entries[j+1].g += self.entries[j].g
                else:
                    merged.append(self.entries[j])
                j += 1
            elif j == len(self.entries):
                # done with entries; now only considering incoming
                if i+1 < len(incoming) and\
                   incoming[i].g + incoming[i+1].g + incoming[i+1].delta <= removal_threshold: 
                    incoming[i+1].g += incoming[i].g
                else:
                    merged.append(incoming[i])
                i += 1
            elif incoming[i].val < self.entries[j].val:
                if incoming[i].g + self.entries[j].g + self.entries[j].delta <= removal_threshold:
                    self.entries[j].g += incoming[i].g
                else:
                    incoming[i].delta = self.entries[j].g + self.entries[j].delta - incoming[i].g 
                    merged.append(incoming[i])
                i += 1
            else:
                if j + 1 < len(self.entries) and\
                   self.entries[j].g + self.entries[j+1].g + self.entries[j+1].delta <= removal_threshold:
                    self.entries[j+1].g += self.entries[j].g
                else:
                    merged.append(self.entries[j])
                j += 1

        self.entries = merged
        self.incoming = []

    def merge(self, other):
        """ Merge another GKArray into the current. The two sketches should have the same 
        epsilon value.

        Parameters:
            other: GKArray
        """
        if self.eps != other.eps:
            raise UnequalEpsilonException("Cannot merge two GKArrays with different epsilon values")

        if other._n == 0:
            self.merge_compress()
            return

        if self._n == 0:
            other.merge_compress()
            self.entries = [Entry(e.val, e.g, e.delta) for e in other.entries]
            self._min = other._min
            self._max = other._max
            self._n = other._n
            self._sum = other._sum
            self._avg = other._avg
            return
             
        entries = []
        spread = int(other.eps*(other._n - 1))
        other.merge_compress()
        g = other.entries[0].g + other.entries[0].delta - spread - 1
        if g > 0:
            entries.append(Entry(other._min, g, 0))
        for i in range(len(other.entries)-1):
            g = other.entries[i+1].g + other.entries[i+1].delta - other.entries[i].delta
            if g > 0:
                entries.append(Entry(other.entries[i].val, g, 0))
        g = spread + 1 - other.entries[len(other.entries) - 1].delta
        if g > 0:
            entries.append(Entry(other.entries[len(other.entries) - 1].val, g, 0))

        self._n += other._n
        self.eps = max(self.eps, other.eps)
        self._min = min(self._min, other._min)
        self._max = max(self._max, other._max)

        self.merge_compress(entries)

    def quantile(self, q):
        """ Return an epsilon-approximate element at quantile q.

        Parameters:
            q: quantile to query for
               0 <= q <= 1
        """
        if q < 0 or q > 1 or self._n == 0:
            return np.nan

        if len(self.incoming) > 0:
            self.merge_compress()

        if self._n < 1.0/self.eps:
            # no need to bother with sketching
            return np.percentile([x.val for x in self.entries], q*100)

        rank = int(q*(self._n - 1) + 1)
        spread = int(self.eps*(self._n - 1))
        g_sum = 0.0
        i = 0
        while i < len(self.entries):
            g_sum += self.entries[i].g
            if g_sum + self.entries[i].delta - 1 > rank + spread:
                    break
            i += 1
        if i == 0:
            return self._min

        return self.entries[i-1].val

    def quantiles(self, q_values):
        """ Return an array of epsilon-approximate elements at each of the quantiles
        q_values.

        Parameters:
            q_values: [] of floats between 0 and 1
        """
        if self._n == 0:
            return [np.NaN]*len(q_values)

        if len(self.incoming) > 0:
            self.merge_compress()

        if self._n < 1.0/self.eps:
            values = [x.val for x in self.entries]
            return [np.percentile(values, q*100) if q >= 0 and q <= 1 else np.NaN for q in q_values]   

        # if q_values are not sorted, call self.quantile() for each
        if q_values != sorted(q_values):
            return [self.quantile(q) for q in q_values]

        #import pdb; pdb.set_trace()
        quantiles = []
        spread = int(self.eps*(self._n - 1))
        g_sum = 0.0
        i, j = 0, 0
        while (i < len(self.entries) and j < len(q_values)):
            g_sum += self.entries[i].g
            while j < len(q_values):
                if q_values[j] < 0 or q_values[j] > 1:
                    quantiles.append(np.NaN)
                    j += 1
                elif g_sum + self.entries[i].delta - 1 > int(q_values[j]*(self._n - 1) + 1) + spread:
                    quantiles.append(self._min if i == 0 else self.entries[i-1].val)
                    j += 1
                else:
                    break
            i += 1
        while j < len(q_values):
            if q_values[j] < 0 or q_values[j] > 1:
                quantiles.append(np.NaN)
            else:
                quantiles.append(self._max)
            j += 1

        return quantiles
