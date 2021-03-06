from keras.layers import LSTM, TimeDistributed, Dense, Embedding, RepeatVector
from keras.models import Sequential

from GAN.embedding import load_discriminator
from GAN.embedding import load_generator
from GAN.helpers.datagen import *
from eval.evaulator import calculate_bleu_score
from helpers.enums import Conf, PreInit


def get_decoder(config):
	# TODO: Hardcoded, move into conf
	nb_words = 1000
	hidden_dim = 1024
	decoder_hidden_layers = 1
	seq_length = 20

	decoder = Sequential()
	decoder.add(LSTM(output_dim=hidden_dim,
					 input_shape=(seq_length, hidden_dim),
					 return_sequences=True))
	for _ in range(1, decoder_hidden_layers):
		decoder.add(LSTM(output_dim=hidden_dim, return_sequences=True))
	decoder.add(TimeDistributed(Dense(output_dim=nb_words, input_shape=(seq_length, hidden_dim), activation='softmax')))
	return decoder


def get_encoder(config):
	# TODO: Hardcoded, move into conf
	nb_words = 1000
	hidden_dim = 1024
	seq_length = 20
	embedding_dimension = 300

	encoder = Sequential()
	embedding_layer = Embedding(nb_words + 2, embedding_dimension, input_length=seq_length,
								trainable=True, mask_zero=True)
	encoder.add(embedding_layer)
	encoder.add(LSTM(output_dim=hidden_dim, input_shape=(seq_length, embedding_dimension),
					 return_sequences=False))
	encoder.add(RepeatVector(seq_length))  # Get the last output of the RNN and repeats it


def load_decoder(config):
	decoder = get_decoder(config)
	decoder.load_weights("300_emb_decoder.hdf5")
	return decoder


def load_encoder_decoder(config):
	model = Sequential()
	model.add(get_encoder(config))
	model.add(get_decoder(config))

	model.load_weights("300_emb_encoder_decoder.hdf5")
	return model


def generator_model(config):
	model = Sequential()
	model.add(LSTM(
		output_dim=config[Conf.EMBEDDING_SIZE],
		input_shape=(config[Conf.MAX_SEQ_LENGTH], config[Conf.NOISE_SIZE]),
		return_sequences=True))

	model.add(TimeDistributed(Dense(config[Conf.VOCAB_SIZE], activation="softmax")))

	return model


def discriminator_model(config):
	model = Sequential()
	model.add(LSTM(
		256,
		input_shape=(config[Conf.MAX_SEQ_LENGTH], config[Conf.VOCAB_SIZE]),
		return_sequences=False,
		dropout_W=0.75,
		dropout_U=0.75))

	model.add(Dense(1, activation="sigmoid"))
	return model


def oh_test_discriminator():
	print "Generating data..."
	index_captions, id_to_word_dict, word_to_id_dict = generate_index_sentences(MAX_SEQUENCE_LENGTH, VOCAB_SIZE,
	                                                                            cap_data=DATASET_SIZE)

	# test_caption = "<sos> boy swimming in water <eos>"
	# test_caption = "<sos> <sos> <sos> <sos> <sos> <sos> <sos> <sos> <sos> <sos> <sos>"
	# print test_caption
	# test_captiontest_caption_one_hot = to_categorical_lists([test_caption_index], MAX_SEQUENCE_LENGTH, NB_WORDS)
	# print test_caption_one_hot


	# test_caption_index = []
	# for word in test_caption.split(" "):
	# 	test_caption_index.append(word_to_id_dict[word])
	# print test_caption_index


	print "Compiling generator..."
	g_model = generator_model()
	g_model.compile(loss='categorical_crossentropy', optimizer="adam", metrics=['binary_accuracy'])
	g_model.load_weights('stored_models/2017-02-23_5000-20-256-first-10--1_g_model-60')
	print g_model.metrics_names

	print "Compiling discriminator..."
	d_model = discriminator_model()
	d_model.trainable = True
	d_model.compile(loss='binary_crossentropy', optimizer="adam", metrics=['binary_accuracy'])
	d_model.load_weights('stored_models/2017-02-23_5000-20-256-first-10--1_d_model-60')
	print d_model.metrics_names

	BATCH_SIZE = 10
	g_input_noise_batch = generate_input_noise(
		BATCH_SIZE,
		noise_mode=NOISE_MODE,
		max_seq_lenth=MAX_SEQUENCE_LENGTH,
		noise_size=NOISE_SIZE)
	index = 0
	index_caption_batch = index_captions[index * BATCH_SIZE:(index + 1) * BATCH_SIZE]
	one_hot_caption_batch = to_categorical_lists(index_caption_batch, config)
	generated_captions_batch = g_model.predict(g_input_noise_batch)

	# Train discriminator
	d_loss_pos = d_model.train_on_batch([one_hot_caption_batch], [1] * BATCH_SIZE)
	d_loss_neg = d_model.train_on_batch([generated_captions_batch], [0] * BATCH_SIZE)

	print "pos: %s" % d_loss_pos
	print "neg: %s" % d_loss_neg
	print "Training discriminator"
	print d_model.predict([one_hot_caption_batch])
	print d_model.predict([generated_captions_batch])


def oh_test_generator(config):
	index = 0

	print "Generating data..."
	index_captions, id_to_word_dict, word_to_id_dict = generate_index_sentences(config)
	index_caption_batch = index_captions[index * config[Conf.BATCH_SIZE]:(index + 1) * config[Conf.BATCH_SIZE]]
	one_hot_caption_batch = to_categorical_lists(index_caption_batch, config)
	softmax_caption = onehot_to_softmax(one_hot_caption_batch)

	g_model = load_decoder(config)
	# g_model.compile(loss='categorical_crossentropy', optimizer="adam")

	print "Setting initial generator weights..."
	np.random.seed(42)
	g_input_noise = generate_input_noise(config)

	predictions = g_model.predict(g_input_noise)

	soft_max_vals = []
	soft_min_vals = []
	pred_max_vals = []
	pred_min_vals = []

	for i in range(10):
		soft_max_vals.append(max(softmax_caption[0][i]))
		soft_min_vals.append(min(softmax_caption[0][i]))
		pred_max_vals.append(max(predictions[0][i]))
		pred_min_vals.append(min(predictions[0][i]))

	max_softs = ""
	for val in soft_max_vals:
		max_softs += "%10.9f\t" % val
	max_preds = ""
	for val in pred_max_vals:
		max_preds += "%10.9f\t" % val
	min_softs = ""
	for val in soft_min_vals:
		min_softs += "%g\t" % val
	min_preds = ""
	for val in pred_min_vals:
		min_preds += "%g\t" % val

	print ""
	print "Max soft:\t%s" % max_softs
	print "Max pred:\t%s" % max_preds
	print ""
	print "Min: soft:\t%s" % min_softs
	print "Min: pred:\t%s" % min_preds
	print ""


def oh_create_generator(config):
	if config[Conf.PREINIT] == PreInit.DECODER:
		print "Setting initial generator weights..."
		g_model = load_decoder(config)
	elif config[Conf.PREINIT] == PreInit.ENCODER_DECODER:
		# TODO: Add code for preinitializing with entire sequence to sequence model
		pass
	else:
		g_model = generator_model(config)
	g_model.compile(loss='categorical_crossentropy', optimizer="adam", metrics=['accuracy'])

	return g_model


def oh_create_discriminator(config):
	d_model = discriminator_model(config)
	d_model.trainable = True
	d_model.compile(loss='binary_crossentropy', optimizer="adam", metrics=['accuracy'])
	return d_model


def oh_predict(config, logger):
	print "Compiling generator..."

	noise_batch = generate_input_noise(config)

	g_model = load_generator(logger)
	d_model = load_discriminator(logger)

	g_model.compile(loss='categorical_crossentropy', optimizer="adam")

	g_weights = logger.get_generator_weights()
	d_weights = logger.get_discriminator_weights()
	print "Num g_weights: %s" % len(g_weights)
	print "Num d_weights: %s" % len(g_weights)

	index_captions, id_to_word_dict, word_to_id_dict = generate_index_sentences(config, cap_data=config[Conf.DATASET_SIZE])
	for i in range(0, len(g_weights), 1):
		g_weight = g_weights[i]
		d_weight = d_weights[i]
		g_model.load_weights("GAN/GAN_log/%s/model_files/stored_weights/%s" % (logger.name_prefix, g_weight))
		d_model.load_weights("GAN/GAN_log/%s/model_files/stored_weights/%s" % (logger.name_prefix, d_weight))

		generated_sentences = g_model.predict(noise_batch[:5])
		generated_classifications = d_model.predict(generated_sentences)
		print "\n\nGENERATED SENTENCES: (%s)\n" % g_weight

		for i in range(len(generated_sentences)):
			prediction = generated_sentences[i]
			sentence = ""
			for softmax_word in prediction:
				id = np.argmax(softmax_word)
				if id == 0:
					sentence += "0 "
				else:
					word = id_to_word_dict[id]
					sentence += word + " "

			print "%5.4f\t%s\n" % (generated_classifications[i][0], sentence)
			# print "%s\tBLEU: %s\n" % (hyp, score)

			# print "Score on real sentence: %s" % fetch_bleu_score(bleu_references, bleu_references[random.randint(0, len(bleu_references)-10)])


def oh_evaluate(config, logger):
	print "Compiling generator..."


	if not config[Conf.LIMITED_DATASET].endswith("_uniq.txt"):
		config[Conf.LIMITED_DATASET] = config[Conf.LIMITED_DATASET].split(".txt")[0] + "_uniq.txt"

	index_captions, id_to_word_dict, word_to_id_dict = generate_index_sentences(config,
	                                                                            cap_data=config[Conf.DATASET_SIZE])
	eval_dataset_string_list_sentences, eval_word_embedding_dict = generate_string_sentences(config)

	g_model = load_generator(logger)
	g_model.compile(loss='categorical_crossentropy', optimizer="adam")
	g_weights = logger.get_generator_weights()

	sentence_count = 10000
	config[Conf.BATCH_SIZE] = sentence_count
	num_weights_to_eval = 0
	epoch_modulo = 3100
	for i in range(1, len(g_weights), 1):
		g_weight = g_weights[i]
		epoch_string = int(g_weight.split("-")[1])
		if epoch_string % epoch_modulo == 0:
			num_weights_to_eval += 1

	noise_batch = generate_input_noise(config)
	print "Num g_weights: %s" % len(g_weights)
	print "Num d_weights: %s" % len(g_weights)
	print "Number of weights to evaluate: %s/%s" % (num_weights_to_eval, len(g_weights))
	for i in range(1, len(g_weights), 1):
	# for i in range(0, len(g_weights), 1):
		g_weight = g_weights[i]
		epoch_string = int(g_weight.split("-")[1])
		if not epoch_string % epoch_modulo == 0:
			continue
		g_model.load_weights("GAN/GAN_log/%s/model_files/stored_weights/%s" % (logger.name_prefix, g_weight))

		generated_sentences = g_model.predict(noise_batch[:sentence_count])
		gen_header_string = "\n\nGENERATED SENTENCES: (%s)\n" % g_weight

		generated_sentences_list = []

		for i in range(len(generated_sentences)):
			prediction = generated_sentences[i]
			generated_sentence = ""
			for softmax_word in prediction:
				id = np.argmax(softmax_word)
				if id == 0:
					generated_sentence += "UNK" + " "
				else:
					word = id_to_word_dict[id]
					generated_sentence += word + " "

			generated_sentences_list.append(generated_sentence)

		print gen_header_string
		for sentence in sorted(generated_sentences_list):
			print sentence
		distinct_sentences = len(set(generated_sentences_list))
		avg_bleu_score, avg_bleu_cosine, avg_bleu_tfidf, avg_bleu_wmd = calculate_bleu_score(generated_sentences_list,
		                                                                                     eval_dataset_string_list_sentences,
		                                                                                     eval_word_embedding_dict)
		print "Number of distict sentences: %s/%s" % (distinct_sentences, sentence_count)
		epoch = g_weight.split("-")[1]
		logger.save_eval_data(epoch, distinct_sentences, sentence_count, avg_bleu_score, avg_bleu_cosine,
		                      avg_bleu_tfidf, avg_bleu_wmd)


def oh_get_training_batch(batch, word_to_id_dict, config):
	tr_one_hot_caption_batch = to_categorical_lists(batch, word_to_id_dict, config)
	# return tr_one_hot_caption_batch
	tr_softmax_caption_batch = onehot_to_softmax(tr_one_hot_caption_batch)
	return tr_softmax_caption_batch
