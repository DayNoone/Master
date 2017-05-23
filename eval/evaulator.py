import numpy as np
from pyemd import emd
from scipy.spatial.distance import cosine
from sklearn.feature_extraction import stop_words
from sklearn.feature_extraction.text import CountVectorizer
from sklearn.metrics import euclidean_distances

from GAN.config import config
from GAN.helpers.datagen import generate_string_sentences
from GAN.helpers.enums import Conf
from bleu import fetch_bleu_score
from eval import tfidf
from helpers.io_helper import load_pickle_file
from helpers.list_helpers import insert_and_remove_last
from word2vec.word2vec_helpers import get_dict_filename

"""

Word embedding distance

"""


def find_n_most_similar_vectors(pred_vector, vector_list, sentence_list, n=5):
	first_vector = vector_list[0]
	first_sentence = sentence_list[0]
	first_mse = compare_vectors(pred_vector, first_vector)

	best_mse_list = [0 for _ in range(n)]
	best_sentence_list = ["" for _ in range(n)]
	best_vector_list = [[] for _ in range(n)]

	best_mse_list = insert_and_remove_last(0, best_mse_list, first_mse)
	best_vector_list = insert_and_remove_last(0, best_vector_list, first_vector)
	best_sentence_list = insert_and_remove_last(0, best_sentence_list, first_sentence)
	for i in range(len(vector_list)):
		temp_vector = vector_list[i]
		temp_mse = compare_vectors(pred_vector, temp_vector)
		for index in range(len(best_vector_list)):
			if temp_mse < best_mse_list[index]:
				best_mse_list = insert_and_remove_last(index, best_mse_list, temp_mse)
				best_vector_list = insert_and_remove_last(index, best_vector_list, temp_vector)
				best_sentence_list = insert_and_remove_last(index, best_sentence_list, sentence_list[i])
				break
	return best_sentence_list


def convert_to_word_embeddings(sentences, word_embedding_dict):
	embedded_sentences = []
	for sentence in sentences:
		embedded_sentence = []
		words = sentence.split(" ")
		for word in words:
			if word in word_embedding_dict:
				embedded_sentence.append(word_embedding_dict[word])
			else:
				embedded_sentence.append(word_embedding_dict['UNK'])

		embedded_sentences.append(embedded_sentence)
	return embedded_sentences


def compare_vectors(v1, v2):
	return cosine(v1, v2)


def convert_vectors(vectors):
	sum_vector = np.zeros(vectors[0].shape)
	for word_emb in vectors:
		sum_vector += word_emb
	return sum_vector


def convert_to_emb_list(dataset_string_list_sentences, word_embedding_dict):
	dataset_emb_list_sentences = []
	for sentence in dataset_string_list_sentences:
		s = []
		for word in sentence:
			if word in word_embedding_dict:
				s.append(word_embedding_dict[word])
			else:
				s.append(word_embedding_dict['UNK'])
		dataset_emb_list_sentences.append(s)
	return dataset_emb_list_sentences


def cosine_distance_retrieval(pred_strings, dataset_string_list_sentences, word_embedding_dict):
	dataset_emb_list_sentences = convert_to_emb_list(dataset_string_list_sentences, word_embedding_dict)
	dataset_single_vector_sentences = [convert_vectors(sentence) for sentence in dataset_emb_list_sentences]
	pred_emb_list_sentences = convert_to_word_embeddings(pred_strings, word_embedding_dict)
	pred_single_vector_sentences = [convert_vectors(sentence) for sentence in pred_emb_list_sentences]

	best_sentence_lists = []
	for pred_single_vector_sentence in pred_single_vector_sentences:
		best_sentence_list = find_n_most_similar_vectors(pred_single_vector_sentence, dataset_single_vector_sentences,
		                                                 dataset_string_list_sentences)
		best_sentence_lists.append([" ".join(x) for x in best_sentence_list])
	return best_sentence_lists


"""

TF-IDF

"""


def tfidf_retrieval(pred_strings, dataset_string_list_sentences):
	table = tfidf.tfidf()
	for dataset_entry in dataset_string_list_sentences:
		table_name = " ".join(dataset_entry)
		table.addDocument(table_name, [str(x) for x in dataset_entry])
	best_sentence_lists = []
	for pred_string in pred_strings:
		similarities = table.similarities(pred_string.split(" "))
		similarities = sorted(similarities, key=lambda x: x[1], reverse=True)
		best_sentence_lists.append([x[0] for x in similarities[:5]])
	return best_sentence_lists


"""

Word bower distance

"""


def get_wmd_distance(d1, d2, word_embedding_dict, min_vocab=7, verbose=False):
	model_vocab = word_embedding_dict.keys()
	vocabulary = [w for w in set(d1.lower().split() + d2.lower().split()) if
	              w in model_vocab and w not in stop_words.ENGLISH_STOP_WORDS]
	if len(vocabulary) < min_vocab:
		return 1
	vect = CountVectorizer(vocabulary=vocabulary).fit([d1, d2])
	feature_names = vect.get_feature_names()
	W_ = np.array([word_embedding_dict[w] for w in feature_names if w in word_embedding_dict])
	D_ = euclidean_distances(W_)
	D_ = D_.astype(np.double)
	D_ /= D_.max()  # just for comparison purposes
	v_1, v_2 = vect.transform([d1, d2])
	v_1 = v_1.toarray().ravel()
	v_2 = v_2.toarray().ravel()
	# pyemd needs double precision input
	v_1 = v_1.astype(np.double)
	v_2 = v_2.astype(np.double)
	v_1 /= v_1.sum()
	v_2 /= v_2.sum()
	if verbose:
		print vocabulary
		print v_1, v_2
	return emd(v_1, v_2, D_)


def wmd_retrieval(pred_strings, dataset_string_list_sentences):
	filename = get_dict_filename(config[Conf.EMBEDDING_SIZE], config[Conf.WORD2VEC_NUM_STEPS],
	                             config[Conf.VOCAB_SIZE], config[Conf.W2V_SET])
	word_embedding_dict = load_pickle_file(filename)

	best_sentence_lists = []

	for pred_string in pred_strings:

		score_tuples = []
		for dataset_string_list_sentence in dataset_string_list_sentences:
			dataset_string = " ".join(dataset_string_list_sentence)
			score = get_wmd_distance(pred_string, dataset_string, word_embedding_dict)
			score_tuples.append((dataset_string, score))
		score_tuples = sorted(score_tuples, key=lambda x: x[1], reverse=False)
		result = [x[0] for x in score_tuples[:5]]

		best_sentence_lists.append(result)

	return best_sentence_lists


from multiprocessing import Pool as ThreadPool
import multiprocessing


def background_wmd_retrieval(pred_strings, dataset_string_list_sentences):
	filename = get_dict_filename(config[Conf.EMBEDDING_SIZE], config[Conf.WORD2VEC_NUM_STEPS],
	                             config[Conf.VOCAB_SIZE], config[Conf.W2V_SET])
	word_embedding_dict = load_pickle_file(filename)
	cpu_count = multiprocessing.cpu_count()
	print "CPUs:", cpu_count
	if cpu_count > 16:
		cpu_count = 15
	pool = ThreadPool(cpu_count)
	tuple_array = [(pred_string, dataset_string_list_sentences, word_embedding_dict) for pred_string in pred_strings]
	best_sentence_lists = pool.map(background_wmd, tuple_array)

	return best_sentence_lists


def background_wmd(tuple):
	pred_string, dataset_string_list_sentences, word_embedding_dict = tuple
	score_tuples = []
	for dataset_string_list_sentence in dataset_string_list_sentences:
		dataset_string = " ".join(dataset_string_list_sentence)
		score = get_wmd_distance(pred_string, dataset_string, word_embedding_dict)
		score_tuples.append((dataset_string, score))
	score_tuples = sorted(score_tuples, key=lambda x: x[1], reverse=False)
	result = [x[0] for x in score_tuples[:5]]
	return result

import time
def calculate_bleu_score(sentences, dataset_string_list_sentences=None, word_embedding_dict=None):
	# print "Evaluating %s generated sentences." % len(sentences)
	if dataset_string_list_sentences is None or word_embedding_dict is None:
		if not config[Conf.LIMITED_DATASET].endswith("_uniq.txt"):
			config[Conf.LIMITED_DATASET] = config[Conf.LIMITED_DATASET].split(".txt")[0] + "_uniq.txt"
		dataset_string_list_sentences, word_embedding_dict = generate_string_sentences(config)

	best_sentence_lists_cosine = cosine_distance_retrieval(sentences, dataset_string_list_sentences,
	                                                       word_embedding_dict)

	best_sentence_lists_tfidf = tfidf_retrieval(sentences, dataset_string_list_sentences)
	start = time.time()
	best_sentence_lists_wmd = background_wmd_retrieval(sentences, dataset_string_list_sentences)
	print "Time used: %s" % (time.time() - start)
	bleu_score_tot_cosine = 0
	for i in range(len(sentences)):
		bleu_score_tot_cosine += fetch_bleu_score(best_sentence_lists_cosine[i], sentences[i])
	avg_bleu_cosine = bleu_score_tot_cosine / float(len(sentences))

	bleu_score_tot_tfidf = 0
	for i in range(len(sentences)):
		bleu_score_tot_tfidf += fetch_bleu_score(best_sentence_lists_tfidf[i], sentences[i])
	avg_bleu_tfidf = bleu_score_tot_tfidf / float(len(sentences))

	bleu_score_tot_wmd = 0
	for i in range(len(sentences)):
		bleu_score_tot_wmd += fetch_bleu_score(best_sentence_lists_wmd[i], sentences[i])
	avg_bleu_wmd = bleu_score_tot_wmd / float(len(sentences))

	avg_bleu_score = (avg_bleu_cosine + avg_bleu_tfidf + avg_bleu_wmd) / 3

	# print "BLEU score cosine:\t", avg_bleu_cosine
	# print "BLEU score tfidf:\t", avg_bleu_tfidf
	# print "BLEU score wmd:\t\t", avg_bleu_wmd
	# print "Avarage BLEU score:", avg_bleu_score
	print "AVG BLEU: %5.4f\t %5.4f,%5.4f,%5.4f (cosine,tfidf,wmd)" % (
	avg_bleu_score, avg_bleu_cosine, avg_bleu_tfidf, avg_bleu_wmd)


def main():
	pred_strings = ["<sos> the flower har large green petals and black stamen <eos> <pad>",
	                "<sos> this flower has yellow petals and middle red stamen <eos> <pad>",
	                "<sos> the are petals the the flower petals <eos> many with petals",
	                "<sos> the are petals the the flower petals <eos> many with petals",
	                "<sos> the are petals the the flower petals <eos> many with petals",
	                "<sos> the are petals the the flower petals <eos> many with petals",
	                "<sos> this flower has many yellow petals with yellow stamen <eos> <pad>",
	                "<sos> stamens are yellow in color with larger anthers <eos> <pad> <pad>"]

	calculate_bleu_score(pred_strings)


if __name__ == '__main__':
	main()
