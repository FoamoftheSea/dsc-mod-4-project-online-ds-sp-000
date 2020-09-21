from arch import arch_model
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from rpy2.robjects import FloatVector
from rpy2.robjects import r
from rpy2.robjects.packages import importr
from statsmodels.tsa.filters.hp_filter import hpfilter

importr('forecast')


def check_autocorrelation(series, lags=None, alpha=0.05):
    from statsmodels.graphics.tsaplots import plot_acf, plot_pacf
    fig, (ax1, ax2) = plt.subplots(2, figsize=(11,9))
    plt.tight_layout()
    plot_acf(series, lags=lags, alpha=alpha, ax=ax1);
    plot_pacf(series, lags=lags, alpha=alpha, ax=ax2);
    plt.show()


def check_pgram(series, show_plot=True):
    '''Generates graph of periodogram for input pandas Series and returns a DataFrame of n_periods of highest spectral density in descending order. Ideal for use in generating a fourier series to describe seasonal movements in time series data.
    '''
    pgram = periodogram(series)
    plt.figure(figsize=(11,4))
    plt.plot(pgram[0], pgram[1], marker='o')
    indices = (-pgram[1]).argsort()[:10]
    results = pd.DataFrame(list(zip((1 / pgram[0][indices]), pgram[1][indices])),
                                 columns=['Period', 'Spec']
                                )
    return results


def fourier_series(data, freqs, K, h=None):
    '''This function will take a pandas DataFrame or Series and produce a fourier series for given frequencies and number of harmonics, either in-sample or forecast.
    
    Params:
    ::data :: (pandas DataFrame or Series) The input data to generate fourier series.
    ::freqs:: (list-like) The frequencies of the data to generate the fourier series.
    ::K    :: (int) The number of harmonics to generate.
    ::h    :: (int) If not None, generates h periods out of sample. If None, generate in-sample.
    '''
    type1 = type(pd.DataFrame())
    type2 = type(pd.Series())
    if type(data) != type1 and type(data) != type2:
        raise ValueError("Input data must be a Pandas DataFrame or Series")
    if type(data) == type1:
        if len(data.columns) > 1:
            raise ValueError("Input DataFrame must have only one column")
        else:
            data = data.iloc[:,0]
    
    from rpy2.robjects.packages import importr
    from rpy2.robjects import FloatVector
    from rpy2.robjects import r
    importr('forecast')
    
    index = data.index
    length = len(data)
    
    #for col in data:
    rlist = FloatVector(data)
    fourier_terms = pd.DataFrame()
    for freq in freqs:
        if not h:
            fs = r['fourier'](r['ts'](rlist, f=freq), K=K)
        else:
            fs = r['fourier'](r['ts'](rlist, f=freq), K=K, h=h)

        length = int(len(fs)/(2*K))
        for i in range(K):
            columns = ['S'+str(i+1)+'-'+str(round(freq, 2)), 
                       'C'+str(i+1)+'-'+str(round(freq, 2))]
            # split sine and cosine values:
            i *= 2
            s = fs[i*length:(i+1)*length]
            c = fs[(i+1)*length:(i+2)*length]
            fourier_terms = pd.concat([fourier_terms, 
                                       pd.DataFrame(list(zip(s,c)), columns=columns)],
                                      axis=1
                                     )
    
    if not h:
        fourier_terms.index = index
    else:
        if data.index.is_all_dates:
            freq = data.index.freqstr
            future_index = pd.date_range(start=data.index[-1], periods=h+1, freq=freq)[1:]
            fourier_terms.index = future_index
    
    return fourier_terms


def get_orders(autoarima_output):
    '''This function takes the output given when using rpy2 to run the auto.arima() function from the 'forecast' package for R. It will convert the output into a string to extract the recommended orders for the ARIMA model, and return them as tuples to be used with python models, namely SARIMAX from statsmodels.
    '''
    string = str(autoarima_output).split('ARIMA')[1].split(' ')[0]
    if len(string) < 8:
        param = tuple(int(x) for x in string.replace('(','').replace(')','').split(','))
        sparam = (0,0,0,0)
    else:
        params = tuple(int(x) for x in string.replace('(','').replace(')',',')
                       .replace('[','').replace(']','').split(','))
        param = params[:3]
        sparam = params[3:]
    
    return param, sparam


def get_coeffs(autoarima):

    names = list(autoarima[0].names)
    order, sorder = get_orders(autoarima)
    sum_orders = order[0] + order[2] + sorder[0] + sorder[2]

    #if 'drift' in names or 'mean' in names or 'intercept' in names:
    #    prms = pd.Series([list(autoarima[0])[-1]] + list(autoarima[0])[:-1] + list(autoarima[1]))
    #    prms.index = ['const'] + names[:-1] + ['sigma2']
    #    #prms.index = [list(autoarima[0].names)[-1]] + list(autoarima[0].names)[:-2] + ['sigma2']
    if len(names) > sum_orders:
        const_names = list(names[sum_orders:])
        order_names = list(names[:sum_orders])
        const_params = list(autoarima[0])[sum_orders:]
        order_params = list(autoarima[0])[:sum_orders]
        prms = pd.Series(const_params + order_params + list(autoarima[1]))
        prms.index = const_names + order_names + ['sigma2']
    else:
        prms = pd.Series(list(autoarima[0]) + list(autoarima[1]))
        prms.index = names + ['sigma2']
    
    return prms


def model_from_autoarima(series, freq=None):
    if freq:
        autoarima = r['auto.arima'](r['ts'](FloatVector(series), freq=freq))
    else:
        autoarima = r['auto.arima'](r['ts'](FloatVector(series)))
        
    order, sorder = get_orders(autoarima)
    params = get_coeffs(autoarima)

    sum_orders = order[0] + order[2] + sorder[0] + sorder[2]

    if (len(params.index) - 1) > sum_orders:
        const_names = list(autoarima[0].names[sum_orders:])
        if len(const_names) > 1:
            print('Multiple constants')
            const_string = ''
            for const_name in const_names:
                const_string += const_name + ' '
        else: 
            const_string = const_names[0]
            const_name = const_names[0]
        print('{}{} model with {}'.format(order, sorder, const_string))

        #if 'intercept' in const_names and 'drift' in const_names:
        #    trend = 'ct'
        #elif 'intercept' in const_names:
        #    trend = 'c'
        #elif 'drift' in const_names:
        #    trend = 'c'
        #if 'intercept' in const_names and 'drift' in const_names:
        #    trend = 'ct'
        #elif 'intercept' in const_names:
        #    trend = 'c'
        #elif 'drift' in const_names:
        #    trend = 't'
        const = pd.Series(np.ones(len(series)))
        const.index = series.index
        const.name = const_name
    else:
        print('{}{} model with no constant'.format(order, sorder))
        const = None
        #trend = None
    
    return order, sorder, params, const


def plot_sarimax_predictions(fit, observed, periods_ahead, dynamic=None, exog=None, alpha=0.05, 
                             ylabel=None, xlabel=None, figsize=None, separate_plots=False, 
                             format_labels=True):
    start = fit.loglikelihood_burn
    pred = fit.get_prediction(start=start)
    mse = np.mean((observed-pred.predicted_mean)**2)

    if not ylabel:
        ylabel = observed.name
        if not ylabel:
            ylabel = 'Series Value'

    if not xlabel:
        xlabel = observed.index.name
        if not xlabel:
            xlabel = 'Time'
            
    if format_labels:
        xlabel = xlabel.replace('_',' ').title()
        ylabel = ylabel.replace('_',' ').title()
        
    print('MSE of fit: {}'.format(mse))
    dyn_string = 'One-step ahead Forecast'
    title_string = ''

    if dynamic:
        pred = fit.get_prediction(dynamic=dynamic)
        dyn_string = 'Dynamic Forecast'
        title_string = ' from {}'.format(str(dynamic))

    pred_conf = pred.conf_int(alpha=alpha).loc[dynamic:]

    # Plot observed values
    if not figsize:
        if not separate_plots:
            figparam = plt.rcParams.get('figure.figsize')
            figsize = (figparam[0], int(figparam[0] * 1.25))
    if separate_plots:
        fig, ax = plt.subplots(figsize=figsize)
    else:
        fig, (ax, ax2) = plt.subplots(2, figsize=figsize)
        #plt.tight_layout()
    
    observed.plot(label='Observed', ax=ax)

    # Plot predicted values  
    pred.predicted_mean.loc[dynamic:].plot(ax=ax, 
                                           label=dyn_string, 
                                           color='orange', 
                                           alpha=0.8)
    # Plot the range for confidence intervals
    ax.fill_between(pred_conf.index, 
                    pred_conf.iloc[:, 0], 
                    pred_conf.iloc[:, 1],
                    alpha=0.3
                   )
    # Set axes labels
    ax.set_title(dyn_string + ' for ' + ylabel + title_string)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.legend()
    
    if separate_plots:
        #plt.legend()
        plt.show()
        fig, ax2 = plt.subplots(figsize=figsize)

    # Let's look at a 5 year forecast with this model
    prediction = fit.get_forecast(periods_ahead, exog=exog)

    # Get confidence intervals of forecasts
    pred_conf = prediction.conf_int()

    # Plot future predictions with confidence intervals
    observed.plot(label='Observed', ax=ax2)
    prediction.predicted_mean.plot(label='Forecasted values', ax=ax2)

    ax2.fill_between(pred_conf.index,
                    pred_conf.iloc[:, 0],
                    pred_conf.iloc[:, 1],
                    alpha=0.3
                   )

    ax2.fill_betweenx(ax.get_ylim(), pred_conf.index[0], pred_conf.index[-1],
                     alpha=0.1,
                     zorder=-1
                    )
    
    ax2.set_title(str(periods_ahead) + ' period ahead forecast for ' + ylabel)
    ax2.set_xlabel(xlabel)
    ax2.set_ylabel(ylabel)
    ax2.legend()
    plt.show()


def so_filter(series, sd_method='rolling', l=None, k=0, lamb=700, center=True, visualize=False,
                hp_filter=True, return_df=False, d=1):
    '''Takes in a pandas series and filters it to become stationary according to the process
    outlined by Stockhammar & Oller (2007). Series passed should be the already differenced
    series (close to stationary but with local trends and heteroscedasticity).
    
    Params:
    ::series:: (pandas Series) input data.
    ::sd_method:: (str) either 'rolling' or 'GARCH'. Method for estimating local SD.
    ::l:: (int) the window size of rolling SD calculation
    ::k:: (int) the window size of mean filtering. If zero, no mean filter is performed.
    ::lamb:: (int) lambda value for hp_filter of SD. Does nothing if hp_filter == False.
    ::center:: (bool) whether to use centered windows for local mean and SD calculation. 
                      Stockhammar & Oller use centered windows in their study.
    ::visualize:: (bool) whether to show plots showing filter process.
    ::hp_filter:: (bool) whether to apply Hodrick-Prescott filter to local SD.
    ::return_df:: (bool) if False, returns filtered series. If True, returns filtered series along
                         with columns containing local means and SDs used in filtering.
    '''
    
    series_mean = series.mean()
    
    if k > 0:
        rolling_means = series.rolling(window=k, center=center).mean()
        mean_filt = series - rolling_means
        rolling_means.name = 'ma'
    else:
        mean_filt = series - series_mean
    
    # Get local stds using Stockhammer & Oller (2007) method
    if sd_method == 'rolling':
        stds = series.rolling(window=l, center=center).std(ddof=1).dropna()
    
    # Get local stds using GARCH
    if sd_method == 'GARCH':
        arch = arch_model(series, 
                      mean='Zero', 
                      vol='GARCH', 
                      #dist='t'
                      rescale=True
                     ).fit()
        stds = arch.conditional_volatility / arch.scale
        print(arch.summary())
    
    # Perform filtering

    if hp_filter:
        stds = pd.DataFrame(hpfilter(stds, lamb=lamb)).T.iloc[:, 1]
        
    stds.name = 'sd'
    
    filtered = series.std() * ((mean_filt) / stds) + series_mean
    filtered = filtered.dropna()
    filtered.name = 'filtered_series'
    
    if visualize:
        fig, (ax1, ax2) = plt.subplots(2, figsize=(11,10), sharex=True)
        series.plot(label=series.name, ax=ax1)
        stds.plot(label='local SD', ax=ax1)
        ax1.set_title('Series with local SD')
        ax1.legend()
        filtered.plot(label=series.name, ax=ax2)
        ax2.set_title('Filtered Series')
        ax2.legend()
        plt.tight_layout()
        plt.show()
        
    results = pd.merge(filtered, stds, left_index=True, right_index=True)
    if k > 0:
        results = pd.merge(results, rolling_means, left_index=True, right_index=True)
    
    if return_df:
        return results
    else:
        return filtered