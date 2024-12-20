from __future__ import print_function
try:
	raw_input
except:
	raw_input = input

import numpy as np
import time
import os
from PIL import Image

from tensorflow.keras.applications.resnet50 import ResNet50, preprocess_input, decode_predictions
from tensorflow.keras.preprocessing import image

RESNET_MEAN = np.array([103.939, 116.779, 123.68])


def orthogonal_perturbation(delta, prev_sample, target_sample):
	perturb = np.random.randn(1, 224, 224, 3)
	perturb /= np.linalg.norm(perturb, axis=(1, 2))
	perturb *= delta * np.mean(get_diff(target_sample, prev_sample))
	diff = (target_sample - prev_sample).astype(np.float32)
	diff /= get_diff(target_sample, prev_sample)
	perturb -= (np.vdot(perturb, diff) / np.linalg.norm(diff)**2) * diff
	overflow = (prev_sample + perturb) - 255 + RESNET_MEAN
	perturb -= overflow * (overflow > 0)
	underflow = -RESNET_MEAN
	perturb += underflow * (underflow > 0)
	return perturb

def forward_perturbation(epsilon, prev_sample, target_sample):
	perturb = (target_sample - prev_sample).astype(np.float32)
	perturb *= epsilon
	return perturb


def get_converted_prediction(sample, classifier):
	sample = (sample + RESNET_MEAN).astype(np.uint8).astype(np.float32) - RESNET_MEAN
	label = decode_predictions(classifier.predict(sample), top=1)[0][0][1]
	return label


def save_image(sample, classifier, folder):
	label = get_converted_prediction(np.copy(sample), classifier)
	sample = sample[0]
	sample += RESNET_MEAN
	sample = sample[..., ::-1].astype(np.uint8)
	sample = Image.fromarray(sample)
	id_no = time.strftime('%Y%m%d_%H%M%S', time.localtime())
	sample.save(os.path.join("images", folder, "{}_{}.png".format(id_no, label)))


def preprocess(sample_path):
	img = image.load_img(sample_path, target_size=(224, 224))
	x = image.img_to_array(img)
	x = np.expand_dims(x, axis=0)
	x = preprocess_input(x)
	return x


def get_diff(sample_1, sample_2):
	return np.linalg.norm(sample_1 - sample_2, axis=(1, 2))


def boundary_attack():
	classifier = ResNet50(weights='imagenet')
	initial_sample = preprocess('images/original/seal.png')
	target_sample = preprocess('images/original/eel.png')
	folder = time.strftime('%Y%m%d_%H%M%S', time.localtime())
	os.mkdir(os.path.join("images", folder))
	save_image(np.copy(initial_sample), classifier, folder)
	attack_class = np.argmax(classifier.predict(initial_sample))
	target_class = np.argmax(classifier.predict(target_sample))

	adversarial_sample = initial_sample
	n_steps = 0
	n_calls = 0
	epsilon = 1.0
	delta = 0.1

	while True:
		trial_sample = adversarial_sample + forward_perturbation(epsilon, adversarial_sample, target_sample)
		prediction = classifier.predict(trial_sample)
		n_calls += 1
		if np.argmax(prediction) == attack_class:
			adversarial_sample = trial_sample
			break
		else:
			epsilon *= 0.9

	while True:
		print("Step #{}...".format(n_steps))
		print("\tDelta step...")
		d_step = 0
		while True:
			d_step += 1
			print("\t#{}".format(d_step))
			trial_samples = []
			for i in np.arange(10):
				trial_sample = adversarial_sample + orthogonal_perturbation(delta, adversarial_sample, target_sample)
				trial_samples.append(trial_sample)
			trial_samples_batch = np.vstack(trial_samples)  # Combine the list of tensors into a single batch tensor
			predictions = classifier.predict(trial_samples_batch)
			n_calls += 10
			predictions = np.argmax(predictions, axis=1)
			d_score = np.mean(predictions == attack_class)
			if d_score > 0.0:
				if d_score < 0.3:
					delta *= 0.9
				elif d_score > 0.7:
					delta /= 0.9
				adversarial_sample = np.array(trial_samples)[np.where(predictions == attack_class)[0][0]]
				break
			else:
				delta *= 0.9
		print("\tEpsilon step...")
		e_step = 0
		while True:
			e_step += 1
			print("\t#{}".format(e_step))
			trial_sample = adversarial_sample + forward_perturbation(epsilon, adversarial_sample, target_sample)
			prediction = classifier.predict(trial_sample)
			n_calls += 1
			if np.argmax(prediction) == attack_class:
				adversarial_sample = trial_sample
				epsilon /= 0.5
				break
			elif e_step > 500:
					break
			else:
				epsilon *= 0.5

		n_steps += 1
		chkpts = [1, 5, 10, 50, 100, 500]
		if (n_steps in chkpts) or (n_steps % 500 == 0):
			print("{} steps".format(n_steps))
			save_image(np.copy(adversarial_sample), classifier, folder)
		diff = np.mean(get_diff(adversarial_sample, target_sample))
		if diff <= 1e-3 or e_step > 500:
			print("{} steps".format(n_steps))
			print("Mean Squared Error: {}".format(diff))
			save_image(np.copy(adversarial_sample), classifier, folder)
			break

		print("Mean Squared Error: {}".format(diff))
		print("Calls: {}".format(n_calls))
		print("Attack Class: {}".format(attack_class))
		print("Target Class: {}".format(target_class))
		print("Adversarial Class: {}".format(np.argmax(prediction)))


if __name__ == "__main__":
	boundary_attack()
