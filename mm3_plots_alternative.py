import os,sys
import cPickle as pkl
import argparse
import yaml
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import matplotlib.ticker
from scipy.stats.stats import pearsonr
from scipy.stats.stats import spearmanr
from scipy.stats import iqr
from scipy import signal

import mm3_helpers as mm3

# global settings
plt.rcParams['axes.linewidth']=0.5

############################################################################
# functions
############################################################################
def correlation_pearsonr(x,y):
    N=len(x)
    xft=np.fft.fft(x)
    yft=np.fft.fft(y)
    zft=xft*np.conjugate(yft)
    mass=np.real(np.sum(np.fft.fft(np.ones(N))))
    x0=np.float_(np.real(xft[0]/mass))
    y0=np.float_(np.real(yft[0]/mass))
    x2=np.float_(np.real(np.sum(xft*np.conjugate(xft))))/mass**2
    y2=np.float_(np.real(np.sum(yft*np.conjugate(yft))))/mass**2
    z=np.float_(np.real(np.fft.ifft(zft))/mass)

    vx=x2-x0**2
    vy=y2-y0**2

    return (z-x0*y0)/np.sqrt(vx*vy)

def histogram(X,density=True):
    valmax = np.max(X)
    valmin = np.min(X)
    iqrval = iqr(X)
    nbins_fd = (valmax-valmin)*np.float_(len(X))**(1./3)/(2.*iqrval)
    if (nbins_fd < 1.0e4):
        return np.histogram(X,bins='auto',density=density)
    else:
        return np.histogram(X,bins='sturges',density=density)

def make_binning(x,y,bincount_min):
    """
    Given a graph (x,y), return a graph (x_binned, y_binned) which is a binned version
    of the input graph, along x. Standard deviations per bin for the y direction are also returned.
    """
    idx = np.argsort(x)
    x = x[idx]
    y = y[idx]

    valmax = np.max(x)
    valmin = np.min(x)
    iqrval = iqr(x)
    nbins_fd = (valmax-valmin)*np.float_(len(x))**(1./3)/(2.*iqrval)
    if (nbins_fd < 1.0e6):
        histx, bins = np.histogram(x,bins='auto')
    else:
        histx, bins = np.histogram(x,bins='sturges')
#    bins = np.linspace(x[0],x[-1],nbins)
    digitized = np.digitize(x,bins)
    x_binned=[]
    y_binned=[]
    std_binned=[]
    for i in range(1,len(bins)):
        ypts = y[digitized == i]

        if (len(ypts) < bincount_min):
            continue

        x_binned.append(float(0.5*(bins[i-1] + bins[i])))
        y_binned.append(float(np.mean(ypts)))
        std_binned.append(float(np.sqrt(np.var(ypts))))

    res = {}
    res['x'] = x_binned
    res['y'] = y_binned
    res['err'] = std_binned
    return res

def get_derivative(X,Y,p=3,deg=1, fits=False):
    X2 = []
    Y2 = []
    Xfit = []
    Yfit = []
    for i in np.arange(len(X))[p:-p]:
        Xtp = X[i-p:i+p+1]
        Ytp = Y[i-p:i+p+1]
        pf = np.polyfit(Xtp,Ytp,deg)
        pfd = np.poly1d(np.polyder(pf,1))
        xfit = np.linspace(Xtp[0],Xtp[-1],10)
        yfit = np.poly1d(pf)(xfit)
        X2.append(X[i])
        Y2.append(pfd(X[i]))
        Xfit.append(xfit)
        Yfit.append(yfit)
    if fits:
        return np.array(X2),np.array(Y2),Xfit,Yfit
    else:
        return np.array(X2),np.array(Y2)

def lineage_byfov_bypeak(lineages, cells, fov=None, peaks=None):
    if (fov == None):
        return lineages

    selection = []
    for lin in lineages:
        cellref = cells[lin[0]]
        if (cellref.fov == fov):
            if not (peaks is None):
                if (cellref.peak in peaks):
                    selection.append(lin)
            else:
                selection.append(lin)

    return selection

def plot_lineages_byfov(lineages,cells,fileoutspl, color='black', lw=0.5, ax_height=3, ax_width_per_hour=2, fovs=None):
    # all cells
    if (fovs == None):
        all_lineages = np.concatenate(lineages)
        fovs = {fov: None for fov in np.unique([cells[key].fov for key in all_lineages])}

    for fov in fovs:
        # determine correct lineages

        if fovs[fov] == None:
            peaks = np.unique([cells[key].peak for key in np.concatenate(lineage_byfov_bypeak(lineages,cells,fov=fov))])
            fovs[fov] = peaks
        peaks = fovs[fov]
        selection = lineage_byfov_bypeak(lineages,cells, fov=fov, peaks=peaks)
        nlin = len(selection)
        npeaks = len(peaks)
        min_bypeak = {}
        max_bypeak = {}
        for lin in selection:
            cellref = cells[lin[0]]
            peak = cellref.peak
            tstart = np.min([cells[key].birth_time for key in lin])
            tend = np.max([cells[key].division_time for key in lin])
            try:
                tmin = min_bypeak[peak]
                if (tstart < tmin):
                    min_bypeak[peak] = tstart
            except KeyError:
                min_bypeak[peak] = tstart
            try:
                tmax = max_bypeak[peak]
                if (tend > tmax):
                    max_bypeak[peak] = tend
            except KeyError:
                max_bypeak[peak] = tend

        deltamax = np.max([max_bypeak[p] - min_bypeak[p] for p in peaks]) / 60.
        figsize = deltamax*ax_width_per_hour,npeaks*ax_height
        if figsize[0] < ax_width_per_hour:
            figsize = ax_width_per_hour, figsize[1]
        fig = plt.figure(num='none', facecolor='w', figsize=figsize)
        gs = gridspec.GridSpec(npeaks,1)

        cell = cells[lineages[0][0]]
        scale = cell.sb / cell.lengths[0]

        for i,peak in enumerate(peaks):
            ax = fig.add_subplot(gs[i,0])
            for lin in lineage_byfov_bypeak(lineages, cells, fov=fov, peaks=[peak]):
                for key in lin:
                    cell = cells[key]
                    X = np.array(cell.times_min)
                    Y = np.array(cell.lengths)
                    Y *= scale
                    ax.plot(X, Y, '-', color=color, lw=lw)
                for keym,keyd in zip(lin[:-1],lin[1:]):
                    cellm = cells[keym]
                    celld = cells[keyd]
                    x0 = np.array(cellm.times)[-1]
                    y0 = np.array(cellm.lengths)[-1]
                    x1 = np.array(celld.times)[0]
                    y1 = np.array(celld.lengths)[0]
                    y0 *= scale
                    y1 *= scale
                    ax.plot([x0,x1],[y0, y1], '--', color=color, lw=lw)

            ax.annotate("peak = {:d}".format(cell.peak), xy=(0.,0.98), xycoords='axes fraction', ha = 'left', va='top', fontsize='x-small')
            ax.set_xlabel('time [min]', fontsize='x-small')
            ax.set_ylabel('length $[\mu m]$',fontsize='x-small')
            #ax.tick_params(length=2)
            ax.tick_params(axis='both', labelsize='xx-small', pad=2)
            ax.spines['right'].set_visible(False)
            ax.spines['top'].set_visible(False)

        fig.suptitle("FOV {:d}".format(fov), fontsize='medium')
        rect = [0.,0.,1.,0.98]
        gs.tight_layout(fig,rect=rect)
        fileout = "{}_xy{:03d}.pdf".format(fileoutspl,fov)
        print "{:<20s}{:<s}".format('fileout',fileout)
        fig.savefig(fileout,bbox_inches='tight',pad_inches=0)
        plt.close('all')
    return

def plot_lineage_with_growth_rate(lineage, cells, fileoutspl, stitch=False, color='black', color1='darkblue', color2='darkgreen', lw=0.5, ms=1, logscale=True, pfit=2, showfits=False, acf_dtau_max=2, T_filter=None):
    """
    plot lineage.
    plot growth rate.
    plot growth rate distribution.
    plot growth rate autocorrelation.
    """

    # some information
    cell_tp = cells[lineage[0]]
    fov = cell_tp.fov
    peak = cell_tp.peak
    ncell = len(lineage)
    tstart = np.min([cells[key].birth_time for key in lineage])
    tend = np.max([cells[key].division_time for key in lineage])

    # figure
    fig = plt.figure(num='none', facecolor='w')
    gs = gridspec.GridSpec(2,2, width_ratios=[3,1.5])
    ax_left_top = fig.add_subplot(gs[0,0])
    ax_left_bot = fig.add_subplot(gs[1,0])
    ax_right_top = fig.add_subplot(gs[0,1])
    ax_right_bot = fig.add_subplot(gs[1,1])

    # fill-in first axes
    ## plot growth curves
    ax = ax_left_top
    XX = []
    YY = []
    YYs = []
    ZZ = [] # hold line for constant gr per generation
    ZZs = []
    GR = []

    cell = cells[lineage[0]]
    Sref = cell.sb
    scale = cell.sb / cell.lengths[0]

    for key in lineage:
        cell = cells[key]
        X = np.array(cell.times_min)
        Y = np.array(cell.lengths) * scale
        gr = cell.growth_rate
        y0 = np.exp(cell.growth_rate_intercept) * scale
        Z = y0*np.exp(gr*(X-X[0]))
        GR.append(gr)

        fac = Sref/Y[0]
        Ys = Y*fac
        Sref = Ys[-1]
        Zs = y0*fac*np.exp(gr*(X-X[0]))

        XX.append(X)
        YY.append(Y)
        YYs.append(Ys)
        ZZ.append(Z)
        ZZs.append(Zs)

        if not stitch:
            ax.plot(X, Y, '.', color=color, ms=ms)
            ax.plot(X, Z, '-', color=color2, lw=lw)

    for i in range(ncell-1):
        x0 = XX[i][-1]
        x1 = XX[i+1][0]
        if stitch:
            ax.axvline(x=0.5*(x0+x1), linestyle='--', color=color, lw=lw)
        else:
            y0 = YY[i][-1]
            y1 = YY[i+1][0]
            ax.plot([x0,x1],[y0, y1], '--', color=color, lw=lw)

    Xs = []
    Ys = []
    Zs = []
    for x, ys, zs in zip(XX,YYs,ZZs):
        Xs = np.append(Xs,x)
        Ys = np.append(Ys,ys)
        Zs = np.append(Zs,zs)

    if stitch:
        ax.plot(Xs, Ys, '.', color=color, ms=ms)
        ax.plot(Xs, Zs, '-', color=color2, lw=lw)

    if logscale:
        ax.set_yscale('log', basey=2)

    ax.set_xlabel('time [min]', fontsize='x-small')
    ax.set_ylabel('length $[\mu m]$',fontsize='x-small')
    #ax.tick_params(length=2)
    ax.tick_params(axis='both', labelsize='xx-small', pad=2)
    ax.spines['right'].set_visible(False)
    ax.spines['top'].set_visible(False)

    ## plot growth rate
    ax = ax_left_bot
    # plot generation growth rates
    for x, gr in zip(XX,GR):
        ax.plot([x[0],x[-1]],[gr*60,gr*60], '-', color=color2, lw=lw)

    # compute instantaneous growth rates
    Zs = np.log(Ys)
    pf = np.polyfit(Xs,Zs,deg=1)
    Xfit = np.linspace(np.min(Xs),np.max(Xs),100)
    Zfit = np.poly1d(pf)(Xfit)
    Yfit = np.exp(Zfit)
    gr_glb = pf[0]

    X1, Z1, X1fits, Z1fits = get_derivative(Xs,Zs,p=pfit,deg=1, fits=True)

    ax.plot(X1, Z1*60, '--', color=color1, lw=lw)

    # filter
    #wn = 0.05
    tmax = np.max(X1)
    tmin = np.min(X1)
    tnyq = (tmax-tmin)/len(X1) # sampling time
    if (T_filter == None):
        T_filter = np.log(2.)/gr_glb
    fn = 0.5/T_filter
    fnyq = 0.5/ tnyq # the fastest frequency is when a cosine performs one half-cycle per sampling time. There is no sense in authorizing fluctuations faster than the sampling interval.
    wn = fn/fnyq
    #print "wn = {:.4f}".format(wn)
    b, a = signal.butter(3, wn) # second argument is in unit of the nyquist frequency = 1/2 1/N (N = len(sample)). The input given in minutes is therefore the half period of the fastest sine wave. A good rule of thumb seems to be choosing a half-period which is ~1 generation time. first argument is the order of the low-pass filter.
    Z1_fil = signal.filtfilt(b,a, Z1,method='gust')
    ax.plot(X1, Z1_fil*60, '-', color=color1, lw=2.*lw)
    """
    Ys_fil = signal.filtfilt(b,a, Ys ,method='gust')
    Zs_fil = np.log(Ys_fil)
    X1_fil, Z1_fil = get_derivative(Xs,Zs_fil,p=pfit,deg=1)
    ax.plot(X1_fil, Z1_fil*60, '-', color=color, lw=2.*lw)
    ax_left_top.plot(Xs,Ys_fil,'b-', lw=lw)
    """
    # filter

    if stitch:
        ax_left_top.plot(Xfit,Yfit,'r--', lw=lw, label='$\lambda = {:.2f}$ $[h^{{-1}}]$'.format(gr_glb*60))
        ax_left_top.legend(loc='best', fontsize='x-small')
        if showfits:
            #for x1fit, z1fit in zip(X1fits,Z1fits)[::2*(pfit + 1)]:
            Zs_fil = [Zs[pfit]]
            Xs_fil = [Xs[pfit]]
            z = Zs_fil[-1]
            for x0,x1,dz in zip(Xs[pfit:-pfit-1], Xs[pfit+1:-pfit], Z1_fil):
                dx = x1-x0
                z += dz*dx
                Zs_fil.append(z)
                Xs_fil.append(x1)

            ax_left_top.plot(Xs_fil, np.exp(Zs_fil), '-b', lw=lw)
            for x1fit, z1fit in zip(X1fits,Z1fits):
                y1fit = np.exp(z1fit)
                ax_left_top.plot(x1fit,y1fit, '-g', lw=lw)

    for i in range(ncell-1):
        x0 = XX[i][-1]
        x1 = XX[i+1][0]
        ax.axvline(x=0.5*(x0+x1), linestyle='--', color=color, lw=lw)

    time = X1[:]
    growth_rates_raw = Z1[:]
    growth_rates_fil = Z1_fil[:]
    growth_rates_gen = np.array(GR)[:]
    gr_mean_gen = np.mean(growth_rates_gen)
    gr_std_gen = np.std(growth_rates_gen)
    gr_cv_gen = gr_std_gen / gr_mean_gen
    gr_mean_fil = np.mean(growth_rates_fil)
    gr_std_fil = np.std(growth_rates_fil)
    gr_cv_fil = gr_std_fil / gr_mean_fil
    tau = np.log(2.)/gr_glb
    ax.axhline(y=gr_glb*60, color=color, linestyle='--', lw=lw, label="$<\lambda> = {:.2f}$ $[h^{{-1}}]$\n$\\tau = {:.0f}$ [min]".format(gr_glb*60, tau))
    ax.legend(loc='best', fontsize='x-small')

    ax.set_xlabel('time [min]', fontsize='x-small')
    ax.set_ylabel('growth rate $[h^{-1}]$',fontsize='x-small')
    #ax.tick_params(length=2)
    ax.tick_params(axis='both', labelsize='xx-small', pad=2)
    ax.spines['right'].set_visible(False)
    ax.spines['top'].set_visible(False)

    # fill-in other axes

    ## histogram
    ax = ax_right_top

    hist,edges = histogram(growth_rates_gen*60., density=True)
    #ax.bar(left=edges[:-1], height=hist, width=edges[1:]-edges[:-1], linestyle='-', color='none', edgecolor=color, lw=lw)
    label = "$\mu$ = {:.2f}, CV = {:<.0f}%".format(gr_mean_gen*60,gr_cv_gen*100.)
    ax.bar(left=edges[:-1], height=hist, width=edges[1:]-edges[:-1], linestyle='-', color=color2, edgecolor='none', lw=0., alpha=0.7, label=label)

    hist,edges = histogram(growth_rates_fil*60., density=True)
    #ax.plot(edges[:-1], hist, '-', color=color, lw=lw)
    #ax.bar(left=edges[:-1], height=hist, width=edges[1:]-edges[:-1], linestyle='-', color='none', edgecolor=color, lw=lw)
    label = "$\mu$ = {:.2f}, CV = {:<.0f}%".format(gr_mean_fil*60,gr_cv_fil*100.)
    ax.bar(left=edges[:-1], height=hist, width=edges[1:]-edges[:-1], linestyle='-', color=color1, edgecolor='none', lw=0., alpha=0.5, label=label)

    #text = "Mean = {:.2f} ({:.2f}) $[h^{{-1}}]$\nCV = {:<.0f}% ({:<.0f}%)".format(gr_mean*60,gr_mean_fil*60, gr_cv*100., gr_cv_fil*100)
    #ax.set_title(text, fontsize='x-small')
    ax.legend(loc='best', fontsize='xx-small')
    ax.set_yticks([])
    ax.set_xlabel('growth rate $[h^{-1}]$', fontsize='x-small')
    ax.set_ylabel('pdf', fontsize='x-small')
    #ax.tick_params(length=2)
    ax.tick_params(axis='both', labelsize='xx-small', pad=2)
    ax.spines['right'].set_visible(False)
    ax.spines['top'].set_visible(False)

    ## autocorrelation function
    ax = ax_right_bot

    #r_gr=correlation_pearsonr(growth_rates,growth_rates)
#    r_gr_fil=correlation_pearsonr(growth_rates_fil,growth_rates_fil)
#
#    idx = ((time - time[0]) <= acf_dtau_max*tau)
#    X=time[idx] - time[0]
#    Y=r_gr[idx]
#    Y_fil=r_gr_fil[idx]
#    M = len(X)
#    npts=1000
#    dn = max(1,np.int_(np.float_(M)/npts))
#    X=X[::dn]
#    Y=Y[::dn]
#    ax.plot(X,Y,'-.', color=color, lw=lw)
#    ax.plot(X,Y_fil,'-', color=color, lw=lw)
#
#    k0 = np.argmin(np.abs(X-tau))
#    x0 = X[k0]
#    y0 = Y[k0]
#    ax.axvline(x=x0, lw=lw, linestyle='--', color=color)
#    text = "$r_{{PE}}(\\tau) = {:.1f}$".format(y0)
#    ax.annotate(text, xy=(x0,y0), xycoords='data', xytext=(1.,0.98), textcoords='axes fraction', fontsize='x-small', ha='right', va='top')

    ax.set_xlabel('time [min]', fontsize='x-small')
    ax.set_ylabel('ACF', fontsize='x-small')
    #ax.tick_params(length=2)
    ax.tick_params(axis='both', labelsize='xx-small', pad=2)
    ax.spines['right'].set_visible(False)
    ax.spines['top'].set_visible(False)

    fig.suptitle("FOV {:d}{:4s}peak = {:d}".format(fov,',',peak), fontsize='medium')
    rect = [0.,0.,1.,0.98]
    gs.tight_layout(fig,rect=rect)
    fileout = "{}_xy{:03d}p{:04d}t{:d}-{:d}.pdf".format(fileoutspl,fov,peak,tstart,tend)
    print "{:<20s}{:<s}".format('fileout',fileout)
    fig.savefig(fileout,bbox_inches='tight',pad_inches=0)
    plt.close('all')
    return

def plot_distributions(cells, attrdict, fileout, color='darkblue', nbins_max=8):
    if (type(attrdict) != dict) or (len(attrdict) == 0):
        print "List of observables empty!"
        return

    # make figure
    attributes = attrdict.keys()
    ncol = len(attributes)
    r = 1.
    fig = plt.figure(num='none',facecolor='w', figsize=(ncol*r*3,3))

    gs = gridspec.GridSpec(1,ncol,wspace=0.0,hspace=0.0)
    for col in range(ncol):
        # choose attribute
        print "col {:d}".format(col)
        attr = attributes[col]

        # build data
        X = []
        for key,cell in cells.items():
            try:
                x = np.float_(getattr(cell,attr))
                if np.isfinite(x):
                    X.append(x)
            except ValueError:
                continue
        X = np.array(X)

        # rescale
        try:
            scale = attrdict[attr]['scale']
            X = X *scale
        except KeyError:
            pass

        #print len(X)
        mean = np.mean(X)
        std = np.std(X)
        cv = std/mean
        hist,edges = histogram(X)
        left = edges[:-1]
        right = edges[1:]
        idx = (hist != 0.)

        # add plot
        ax = fig.add_subplot(gs[0,col])
        #ax.bar(left=left, height=hist, width=right-left, color='none', lw=0.0, edgecolor=thecolor, alpha=0.6)
        ax.plot(left[idx], hist[idx], '-', color=color, lw=1)

        # annotations
        text = "Mean = {:.4g}\nCV = {:<.0f}%".format(mean,cv*100.)
        ax.set_title(text, fontsize='small')
        #ax.annotate(text,xy=(0.05,0.98),xycoords='axes fraction',ha='left',va='top',color=thecolor, fontsize=fontsize)
        xticks = [mean-std,mean,mean+std]
        #ax.set_xticks(xticks)
        ax.set_yticks([])
        try:
            ax.set_xlabel(attrdict[attr]['label'], fontsize='medium')
        except KeyError:
            ax.set_xlabel(attr, fontsize='medium')
        #ax.set_ylabel('length',fontsize='x-small')
        #ax.tick_params(length=2)
        ax.xaxis.set_major_locator(matplotlib.ticker.MaxNLocator(nbins=nbins_max))
        ax.tick_params(axis='both', labelsize='xx-small', pad=2)
        ax.spines['right'].set_visible(False)
        ax.spines['top'].set_visible(False)

    rect = [0.,0.,1.,0.98]
    gs.tight_layout(fig,rect=rect)
    print "{:<20s}{:<s}".format('fileout',fileout)
    fig.savefig(fileout,bbox_inches='tight',pad_inches=0)
    plt.close('all')

    return

def plot_cross_correlations(cells, attrdict, fileout, color1='darkblue', color2='black', nbins_max=8, method='pearsonr', scatter_max_pts=1000, ms=2, bincount_min=10):
    if (type(attrdict) != dict) or (len(attrdict) == 0):
        print "List of observables empty!"
        return

    # make figure
    attributes = attrdict.keys()
    n = len(attributes)
    r = 1.
    fig = plt.figure(num='none',facecolor='w', figsize=(n*r*3,n*3))
    gs = gridspec.GridSpec(n,n,wspace=0.0,hspace=0.2)

    for row in range(n):
        for col in range(n):
            # choose attribute
            print "row {:d} col {:d}".format(row,col)
            attr_row = attributes[row]
            attr_col = attributes[col]

            # build data
            X = []
            Y = []
            for key,cell in cells.items():
                try:
                    x = np.float_(getattr(cell,attr_col))
                    y = np.float_(getattr(cell,attr_row))
                    if np.isfinite(x) and np.isfinite(y):
                        X.append(x)
                        Y.append(y)
                except ValueError:
                    continue
            X = np.array(X)
            #print len(X)
            Y = np.array(Y)

            # rescale
            try:
                scale = attrdict[attr_col]['scale']
                X = X * scale
            except KeyError:
                pass

            try:
                scale = attrdict[attr_row]['scale']
                Y = Y * scale
            except KeyError:
                pass

            xmean = np.mean(X)
            xstd = np.std(X)
            ymean = np.mean(Y)
            ystd = np.std(Y)

            # add plot
            ax = fig.add_subplot(gs[row,col])

            if (col == row):
                hist,edges = histogram(X)
                left = edges[:-1]
                right = edges[1:]
                idx = (hist != 0.)
                ax.plot(left[idx], hist[idx], '-', color=color1, lw=1)

                xticks = [xmean - xstd, xmean, xmean + xstd]
                ax.set_xticks(xticks)
                ax.tick_params(axis='x', which='both', bottom='on', top='off')
                #ax.xaxis.set_major_locator(matplotlib.ticker.MaxNLocator(nbins=nbins_max))
                ax.xaxis.set_major_formatter(matplotlib.ticker.StrMethodFormatter('{x:.2g}'))

            else:
                X = (X-xmean)/xstd
                Y = (Y-ymean)/ystd
                idx = np.random.permutation(np.arange(len(X)))[:scatter_max_pts]
                ax.plot(X[idx],Y[idx],'.', ms=ms,color=color1,alpha=0.8)

                if (method == 'pearsonr'):
                    us = 'PE'
                    corr,pvalue = pearsonr(X,Y)
                elif (method == 'spearmanr'):
                    us = 'SP'
                    corr,pvalue = spearmanr(X,Y)
                else:
                    raise ValueError
                ax.annotate('$r_{{{:s}}} = {:<.2f}$'.format(us,corr),xy=(0.5,1.0),xycoords='axes fraction', ha='center',va='top', color=color2, fontsize='small')

                ## make linear fit to binned data
                ### define the binned data set
                res = make_binning(X, Y, bincount_min)
                x_binned = res['x']
                y_binned = res['y']
                ax.plot(x_binned,y_binned, '-o', color=color2, ms=3*ms, lw=1, alpha=1.0)

                ax.set_xticks([])
                ax.tick_params(axis='x', which='both', bottom='off', top='off')
                ax.axis('equal')
            # end if statement
            ax.set_yticks([])
            ax.tick_params(axis='both', labelsize='xx-small', pad=2)
            ax.tick_params(axis='y', which='both', left='off', right='off')

            ax.spines['right'].set_visible(True)
            ax.spines['top'].set_visible(True)
            ax.spines['left'].set_visible(True)
            ax.spines['bottom'].set_visible(True)

            ## write labels
            if (col == 0):
                label = attrdict[attr_row]['label']
                ax.annotate(label, xy=(-0.10,0.5), xycoords='axes fraction', ha='right', va='center', fontsize='medium')

            if (row == 0):
                label = attrdict[attr_col]['label']
                ax.annotate(label, xy=(0.5,1.10), xycoords='axes fraction', ha='center', va='bottom', fontsize='medium')

    rect = [0.,0.,1.,0.98]
    #gs.tight_layout(fig,rect=rect)
    print "{:<20s}{:<s}".format('fileout',fileout)
    fig.savefig(fileout,bbox_inches='tight',pad_inches=0)
    plt.close('all')

    return

def plot_autocorrelations(cells, attrdict, fileout, color1='darkblue', color2='black', nbins_max=8, method='pearsonr', scatter_max_pts=1000, ms=2, bincount_min=10):
    if (type(attrdict) != dict) or (len(attrdict) == 0):
        print "List of observables empty!"
        return

    # make figure
    attributes = attrdict.keys()
    n = len(attributes)
    r = 1.
    fig = plt.figure(num='none',facecolor='w', figsize=(n*r*3,3))
    gs = gridspec.GridSpec(1,n,wspace=0.0,hspace=0.2)

    for col in range(n):
        # choose attribute
        print "col {:d}".format(col)
        attr = attributes[col]

        # build data
        X = []
        Y = []
        for key,cell in cells.items():
            try:
                keym=cell.parent
                cellm = cells[keym]
                x = np.float_(getattr(cellm,attr))
                y = np.float_(getattr(cell,attr))
                if np.isfinite(x) and np.isfinite(y):
                    X.append(x)
                    Y.append(y)
            except ValueError:
                # error in isfinite tests
                continue
            except KeyError:
                # error in cellm=cells[keym] statement
                continue
        X = np.array(X)
        Y = np.array(Y)

        # rescale
        try:
            scale = attrdict[attr]['scale']
            X = X * scale
            Y = Y * scale
        except KeyError:
            pass

        # add plot
        ax = fig.add_subplot(gs[0,col])

        idx = np.random.permutation(np.arange(len(X)))[:scatter_max_pts]
        ax.plot(X[idx],Y[idx],'.', ms=ms,color=color1,alpha=0.8)

        if (method == 'pearsonr'):
            us = 'PE'
            corr,pvalue = pearsonr(X,Y)
        elif (method == 'spearmanr'):
            us = 'SP'
            corr,pvalue = spearmanr(X,Y)
        else:
            raise ValueError
        ax.annotate('$r_{{{:s}}} = {:<.2f}$'.format(us,corr),xy=(0.5,1.0),xycoords='axes fraction', ha='center',va='top', color='k', fontsize='small')

        ## make linear fit to binned data
        ### define the binned data set
        res = make_binning(X, Y, bincount_min)
        x_binned = res['x']
        y_binned = res['y']
        ax.plot(x_binned,y_binned, '-o', color=color2, ms=3*ms, lw=1, alpha=1.0)

        try:
            ax.set_xlabel(attrdict[attr]['label_m'], fontsize='medium')
            ax.set_ylabel(attrdict[attr]['label_d'], fontsize='medium')
        except KeyError:
            ax.set_xlabel(attr + ' mother', fontsize='medium')
            ax.set_ylabel(attr + ' daughter', fontsize='medium')
        ax.axis('equal')
        ax.xaxis.set_major_locator(matplotlib.ticker.MaxNLocator(nbins=nbins_max))
        ax.yaxis.set_major_locator(matplotlib.ticker.MaxNLocator(nbins=nbins_max))
        ax.xaxis.set_major_formatter(matplotlib.ticker.StrMethodFormatter('{x:.2g}'))
        ax.yaxis.set_major_formatter(matplotlib.ticker.StrMethodFormatter('{x:.2g}'))
        #ax.set_xticks([])
        #ax.set_yticks([])
        ax.tick_params(axis='both', labelsize='xx-small', pad=2)
        ax.tick_params(axis='x', which='both', bottom='on', top='off')
        ax.tick_params(axis='y', which='both', left='on', right='off')

        ax.spines['right'].set_visible(False)
        ax.spines['top'].set_visible(False)

    rect = [0.,0.,1.,0.98]
    gs.tight_layout(fig,rect=rect)
    print "{:<20s}{:<s}".format('fileout',fileout)
    fig.savefig(fileout,bbox_inches='tight',pad_inches=0)
    plt.close('all')

    return

############################################################################
# main
############################################################################
if __name__ == "__main__":
    parser = argparse.ArgumentParser(prog="Plots of cells measurements.")
    parser.add_argument('pklfile', type=file, help='Pickle file containing the cell dictionary.')
    parser.add_argument('-f', '--paramfile',  type=file, required=True, help='Yaml file containing parameters.')
    parser.add_argument('--distributions',  action='store_true', help='Plot the distributions of cell variables.')
    parser.add_argument('--crosscorrelations',  action='store_true', help='Plot the cross-correlation of cell variables.')
    parser.add_argument('--autocorrelations',  action='store_true', help='Plot the autocorrelation of cell variables.')
    parser.add_argument('-l', '--lineagesfile',  type=file, help='Pickle file containing the list of lineages.')
    namespace = parser.parse_args(sys.argv[1:])
    paramfile = namespace.paramfile.name
    allparams = yaml.load(namespace.paramfile)
    params = allparams['plots']
    cells = pkl.load(namespace.pklfile)
    plot_dist = namespace.distributions
    plot_crosscorr = namespace.crosscorrelations
    plot_autocorr = namespace.autocorrelations

    tdir = os.path.dirname(namespace.pklfile.name)
    print "{:<20s}{:<s}".format('data dir', tdir)
    cellname = os.path.basename(namespace.pklfile.name)
    cellnamespl = os.path.splitext(cellname)[0]
    plotdir = os.path.join(tdir,'plots')
    if not os.path.isdir(plotdir):
        os.makedirs(plotdir)

# plot general statistics
    if plot_dist:
        mm3.information ('Plotting distributions.')
        try:
            fileout = os.path.join(plotdir,'{}_distributions.pdf'.format(cellnamespl))
            plot_distributions(cells, attrdict=params['distributions']['attributes'], fileout=fileout)
        except:
            print "Error with distributions plotting."

    if plot_crosscorr:
        mm3.information ('Plotting cross-correlations.')
        try:
            fileout = os.path.join(plotdir,'{}_cross_correlations.pdf'.format(cellnamespl))
            plot_cross_correlations(cells, attrdict=params['cross correlations']['attributes'], fileout=fileout, **params['cross correlations']['args'])
        except:
            print "Error with cross-correlations plotting."

    if plot_autocorr:
        mm3.information ('Plotting autocorrelations.')
        try:
            fileout = os.path.join(plotdir,'{}_autocorrelations.pdf'.format(cellnamespl))
            plot_autocorrelations(cells, attrdict=params['autocorrelations']['attributes'], fileout=fileout, **params['autocorrelations']['args'])
        except:
            print "Error with autocorrelations plotting."

# lineages
    if namespace.lineagesfile != None:
        mm3.information ('Plotting lineages.')
        lineages = pkl.load(namespace.lineagesfile)

        if 'plot_lineages_byfov' in params:
            lindir = os.path.join(plotdir,'lineages_byfov')
            if not os.path.isdir(lindir):
                os.makedirs(lindir)
            if 'fovs' in params['plot_lineages_byfov']:
                fileoutspl = os.path.join(lindir,'{}_lineages'.format(cellnamespl))
                plot_lineages_byfov(lineages,cells,fileoutspl, **params['plot_lineages_byfov']['args'])


        if 'plot_lineages_individually' in params:
            lindir = os.path.join(plotdir,'lineages_individually')
            if not os.path.isdir(lindir):
                os.makedirs(lindir)
            fileoutspl = os.path.join(lindir,'{}_lineages'.format(cellnamespl))
            if 'fovs' in params['plot_lineages_individually']:
                fovs = params['plot_lineages_individually']['fovs']
                selection = []
                if not (fovs is None):
                    for fov in fovs:
                        peaks = fovs[fov]
                        selection = lineage_byfov_bypeak(lineages, cells, fov=fov, peaks=peaks)
            else:
                selection = lineages

            for lineage in selection:
                plot_lineage_with_growth_rate(lineage,cells,fileoutspl, **params['plot_lineages_individually']['args'])
