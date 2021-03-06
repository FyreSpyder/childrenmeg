import pickle
import pandas as pd
import numpy as np
import mne
import tqdm

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from pathlib import Path
from scipy.stats import linregress
from models import BestSCNN, RaSCNN
from MEGDataset import MEGRawRanges, MEGRawRangesTA, TEST_SUBJECTS, TEST_VG, TEST_PDK, TEST_PA

TESTS = [TEST_PA, TEST_PDK, TEST_VG]
SUBJECT_AGE = [13.71, 4.12, 12.93, 6.66, 8.34, 10.80, 16.54, 15.36, 5.73]
SUBJECT_AGE_BIN = [int(x >= 10) for x in SUBJECT_AGE]
SUBJECT_PART = 6
TEST_PART = 9

# TRAINED_MODEL = Path('/ais/clspace5/spoclab/children_megdata/eeglabdatasets/models/MEGraw/scnn/bin'
#                      '/Fold-2-weights.hdf5')
TRAINED_MODEL = Path('/ais/clspace5/spoclab/children_megdata/eeglabdatasets/models/MEGTAugRaw/alstm/bin/'
                     '/Fold-1-weights.hdf5')
RESTING_DATA = '/ais/clspace5/spoclab/children_megdata/biggerset/resting/{0}/{1}.npy'
ORIGINAL_DATA = '/ais/clspace5/spoclab/children_megdata/Original/{0}/{0}_{1}.ds'
TEST_RAW = '/ais/clspace5/spoclab/children_megdata/test_raw/{0}/{0}_{1}-epo.fif'


def load_raw_subjects():
    epoched_data = dict()
    totals = {t: 0 for t in TESTS}
    for subject in TEST_SUBJECTS:
        for test in TESTS:
            file = Path(TEST_RAW.format(subject, test))
            if file.exists():
                print('Found: ', str(file))
                raw = mne.read_epochs(TEST_RAW.format(subject, test), preload=True)
                # raw = raw.filter(2, 16)
                data = raw.pick_types(meg=True, ref_meg=False).get_data().swapaxes(2, 1)
            else:
                file.parent.mkdir(parents=True, exist_ok=True)
                try:
                    raw = mne.io.read_raw_ctf(ORIGINAL_DATA.format(subject, test), preload=True).filter(0.5, 100)
                except ValueError as e:
                    print(e)
                    break
                events = mne.find_events(raw, mask=0x8, mask_type='and')
                epoch = mne.Epochs(raw, events, tmin=-0.5, tmax=1.5, preload=True,
                                   reject_by_annotation=False).resample(200)
                epoch.save(TEST_RAW.format(subject, test))
                data = epoch.pick_types(meg=True, ref_meg=False).get_data().swapaxes(2, 1)

            epoched_data[(subject, test)] = data[3:, ...]
            totals[test] += epoched_data[(subject, test)].shape[0]

    print('Task amounts:', totals)
    return epoched_data


def noise_occlusion(point, occluded_points, occlusion_weight=0.999):
    occlusion = occlusion_weight * np.random.rand(1, len(occluded_points), point.shape[-1])
    point[:, occluded_points, ...] = (1 - occlusion_weight) * point[:, occluded_points, ...] + occlusion
    return normalize(point)


def normalize(data, ch_axis=-1, eps=1e-12):
    return (data - data.mean(ch_axis, keepdims=True)) / (data.std(ch_axis, keepdims=True) + eps)


def load_rest(subject, test, shape=(700, 151)):
    try:
        return np.load(RESTING_DATA.format(subject, test))
    except FileNotFoundError as e:
        print('Warning: ', e)
        return np.zeros(shape)


def rest_points(fnames, x_shape):
    """
    Generate all the test points in one contiguous unit, as corresponding to the list of filenames.
    :param fnames: List/ndarray of "Path"s for x points
    :param x_shape: Shape for the resulting data to enable pre-allocation
    :return: All rest points as single ndarray with shape equal to x_shape
    """
    rest = np.zeros(x_shape)
    for i, fn in enumerate(fnames):
        rest[i, ...] = load_rest(fn.parts[SUBJECT_PART], fn.parts[TEST_PART])
    return rest


def obscuring_profile(model, x, step=1, runs=10):
    obs_event = np.zeros(((700-step)//step, 2, runs))
    obs_ends = np.zeros(((700-step)//step, 2, runs))
    event_inds = [99, 100]
    end_inds = [[0], [699]]
    for i in tqdm.tqdm(range(step, 700-step, step), desc="Obscuring"):
        if i % 7 == 0:
            event_inds = list(reversed([event_inds[0] - i for i in range(1, step + 1)])) + event_inds
            end_inds[0] += [end_inds[0][-1] + i for i in range(1, step + 1)]
        else:
            end_inds[1] = list(reversed([end_inds[1][0] - i for i in range(1, step + 1)])) + end_inds[1]
            event_inds += [event_inds[-1] + i for i in range(1, step + 1)]

        obs_event[i // step - 1, ...] = np.stack(
            [model.predict(noise_occlusion(x.copy(), event_inds)) for _ in range(runs)], axis=-1
        )
        obs_ends[i // step - 1, ...] = np.stack(
            [model.predict(noise_occlusion(x.copy(), end_inds[0] + end_inds[1]))for _ in range(runs)], axis=-1
        )

    return obs_event, obs_ends


BATCH_SIZE = 64
POINTS_PER_SUBJECT = 20

if __name__ == '__main__':

    # dataset = MEGRawRanges('/ais/clspace5/spoclab/children_megdata/biggerset')
    dataset = MEGRawRangesTA('/ais/clspace5/spoclab/children_megdata/biggerset')

    testset = dataset.testset(batchsize=BATCH_SIZE, fnames=True, flatten=False)

    # model = BestSCNN(dataset.inputshape(), dataset.outputshape())
    model = RaSCNN(dataset.inputshape(), dataset.outputshape())

    model.compile()
    model.load_weights(TRAINED_MODEL)
    model.summary()

    predictions = []
    true_labels = []
    filenames = []
    for i in range(int(np.ceil(testset.n / BATCH_SIZE))):
        fn, _x, y = next(testset)
        true_labels.append(y)
        filenames.append(fn)
        predictions.append(model.predict(_x, batch_size=BATCH_SIZE, verbose=True))

    correct_filter = np.vstack(true_labels).argmax(axis=-1) == np.vstack(predictions).argmax(axis=-1)
    print('Correct Preditions: {}, Incorrect: {}'.format(np.sum(correct_filter), np.sum(correct_filter == 0)))
    print('Un-modified Test Accuracy: ', np.mean(correct_filter))

    correct_pred = np.vstack(predictions)[correct_filter]
    best_confidence = np.argsort(np.max(correct_pred, axis=1))

    filenames = np.vstack(filenames).squeeze()[correct_filter]
    raw = load_raw_subjects()

    x, y = [], []
    subject_perf = {s: np.array([0, 0]) for s in TEST_SUBJECTS}
    for subject, age in zip(TEST_SUBJECTS, SUBJECT_AGE):
        age_bin = int(age > 10)
        for test in TESTS:
            try:
                x.append(raw[(subject, test)])
                y.append(age_bin*np.ones(x[-1].shape[0]))
                preds = model.predict(normalize(raw[(subject, test)]), batch_size=BATCH_SIZE).argmax(axis=-1)
                subject_perf[subject] += [np.sum(preds == age_bin), np.sum(preds == (1 ^ age_bin))]
            except KeyError:
                continue

        acc = subject_perf[subject][0] / np.sum(subject_perf[subject])
        print('{}: {:.2%}, {} -- {}'.format(subject, acc, subject_perf[subject][1], age))

    rest_corr_pred = model.predict(normalize(np.vstack(x)), batch_size=BATCH_SIZE)
    print('Modified Test Accuracy: ', np.mean(np.concatenate(y, axis=0) == rest_corr_pred.argmax(axis=-1)))

    writer = pd.ExcelWriter('event_results/results_multi-rest.xlsx')

    prev_experiments = Path('event_results/dest.pkl')
    if prev_experiments.exists():
        print('Found existing analysis.')
        dest, obs_evnt_profile, obs_ends_profile = pickle.load(prev_experiments.open('rb'))
    else:
        dest = {s: {t: dict() for t in TESTS} for s in TEST_SUBJECTS}

        obs_ends_profile = []
        obs_evnt_profile = []

        # Consider high confidence points
        for subject in tqdm.tqdm(TEST_SUBJECTS, desc="Compiling results"):
            for test in TESTS:
                for conf in reversed(best_confidence):
                    if subject in filenames[conf].parts and test in filenames[conf].parts:
                        epoch = int(filenames[conf].parts[-1].split('.')[0].split('_')[1])
                        print('Subject: {}, Test: {}, Epoch: {}'.format(subject, test, epoch))
                        i = np.argmax(correct_pred[conf, :])

                        # Load all rest points, but only predict on current test
                        rest_x = np.array([load_rest(subject, t)[np.newaxis, ...] for t in TESTS])
                        rest_pred = model.predict(normalize(rest_x[TESTS.index(test)]))[0, i]

                        # Combine rest points
                        rest_x = rest_x.sum(axis=0) / rest_x.shape[0]

                        test_x = raw[(subject, test)][[epoch - 1], ...]
                        x_minus_rest = model.predict(normalize(test_x - rest_x))[0, i]

                        obs_event, obs_ends = obscuring_profile(model, test_x.copy())

                        obs_ends_profile.append(obs_ends[:, i, :])
                        obs_evnt_profile.append(obs_event[:, i, :])

                        dest[subject][test] = dict(test_x=correct_pred[conf, i], rest=rest_pred,
                                                   test_x_minus_rest=x_minus_rest)
                        break

        pickle.dump([dest, obs_evnt_profile, obs_ends_profile], prev_experiments.open('wb'))

    for subject in tqdm.tqdm(TEST_SUBJECTS, desc="Outputting specific results to file"):
        pd.DataFrame.from_dict(dest[subject], orient='index').to_excel(writer, subject,
                                                                       columns=['test_x', 'rest', 'test_x_minus_rest'])
    writer.save()

    obs_evnt_profile = 100*np.stack(obs_evnt_profile, axis=0).mean(axis=0)[:-1, ...]
    obs_ends_profile = 100*np.stack(obs_ends_profile, axis=0).mean(axis=0)[:-1, ...]
    obs_x_sec = np.arange(1/200, 3.5, step=1/200)[:-1]

    # for title, data in zip(('Obscure Event', 'Obscure Ends'), (obs_evnt_profile, obs_ends_profile)):
    ends_mean = obs_ends_profile.mean(axis=-1)
    evnt_mean = obs_evnt_profile.mean(axis=-1)
    plt.fill_between(obs_x_sec, ends_mean - obs_ends_profile.std(axis=-1),
                     ends_mean + obs_ends_profile.std(axis=-1), alpha=0.3, color='b')
    plt.plot(obs_x_sec, ends_mean, 'b', label='Obscure Ends')
    plt.fill_between(obs_x_sec, evnt_mean - obs_evnt_profile.std(axis=-1),
                     evnt_mean + obs_evnt_profile.std(axis=-1), alpha=0.3, color='g')
    plt.plot(obs_x_sec, evnt_mean, 'g', label='Obscure Event')
    plt.legend()
    plt.title('Model Output of Obscured Trials')
    plt.xlabel('Amount Obscured (s)')
    plt.ylabel('Correct Output %')
    plt.savefig('event_results/obscuring_profile.pdf')
    plt.clf()

