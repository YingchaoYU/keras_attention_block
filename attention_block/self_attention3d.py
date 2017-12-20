from collections.abc import Callable
from keras.layers import
from keras import backend as K
from keras import initializers
from keras import activations
from keras.engine.topology import Layer


class SelfAttention3DLayer(Layer):
    """self-attention的特点是自己为输入,输出也是一个和自己一样shape的张量.
    """

    def __init__(self, similarity="additive",
                 kernel_initializer='glorot_uniform',
                 wk_kernel_initializer='glorot_uniform',
                 **kwargs):
        if isinstance(similarity, Callable):
            self.similarity = similarity
        elif isinstance(similarity, str) and similarity in (
                "multiplicative", "dot_product", "additive"):
            self.similarity = similarity
        else:
            raise ValueError(
                'similarity now only support '
                '"multiplicative","dot_product","additive",'
                'and you can input a function as the similarity function!'
            )

        self.kernel_initializer = initializers.get(kernel_initializer)
        self.wk_kernel_initializer = initializers.get(
            wk_kernel_initializer)
        super().__init__(**kwargs)

    def build(self, input_shape):
        if len(input_shape) != 3:
            raise ValueError('A self attention layer should be called '
                             'by a (batch,time_step,dim)3D inputs.'
                             'Got ' + str(input_shape) + ' inputs.')
        if self.similarity == "additive":
            self.kernel = self.add_weight(
                name='kernel',
                shape=(
                    input_shape[-2], input_shape[-2]),
                initializer=self.kernel_initializer,
                trainable=True)
            self.wk_kernel = self.add_weight(
                name='wk_kernel',
                shape=(
                    input_shape[-1], input_shape[-2]),
                initializer=self.wk_kernel_initializer,
                trainable=True)
        elif self.similarity == "multiplicative":
            self.kernel = self.add_weight(
                name='kernel',
                shape=(
                    input_shape[-1], input_shape[-1]),
                initializer=self.kernel_initializer,
                trainable=True)

        # Be sure to call this somewhere!
        super().build(input_shape)

    def multiplicative(self, Source):
        """点乘相似度,在google的attention is all you need 中看到的.\
很迷,没有要训练的矩阵,直接转置点乘

        .. math::  Similarity(Source) =  Source^T\cdot W \cdot Source 
        """
        Source_t = K.permute_dimensions(Source, (0, 2, 1))
        sim = K.dot(K.dot(Source, self.kernel), Source_t)
        return sim

    def dot_product(self, Source):
        r"""点乘相似度,在google的attention is all you need 中看到的.\
很迷,没有要训练的矩阵,直接转置点乘

        .. math::  Similarity(Source) = \frac{Source^T\cdot Source}{\sqrt{d_k}}
        """
        Source_t = K.permute_dimensions(Source, (0, 2, 1))
        sim = K.dot(Source, Source_t) / K.sqrt(Source.shape[-1])
        return sim

    def additive(self, Source):
        """"
        加性相似度,最经典的注意力相似度机制,如果是在self attention中\
则该层有一个dim为Key_time_step的向量和一个(Key_dim,Key_time_step)的矩阵作为用于训练的参数

        .. math::  Similarity(Source) = V \cdot tanh(W_k\cdot Source)
        """
        f_att = K.dot(Source, self.wk_kernel)
        sim = K.dot(K.tanh(f_att), self.kernel)
        return sim

    def call(self, inputs):
        """self-attention就是通过相似度函数计算得的相似矩阵过softmax后与自身点乘得到
        .. math::  A = Softmax(Similarity(Source))
        .. math::  C = A \cdot Source
        """
        Source = inputs
        if isinstance(self.similarity, Callable):
            sim = self.similarity(Source)
        else:
            sim = getattr(self, self.similarity)(Source)
        sm = activations.softmax(sim)
        sm_t = K.permute_dimensions(sm, (0, 2, 1))
        result = K.batch_dot(sm_t, Source)
        return result

    def compute_output_shape(self, input_shape):
        return input_shape


def MultiHeadSelfAttention3DBlock(num_units, num_heads=8,
                                  activation="relu", input_shape=None):
    if K.backend() != 'tensorflow':
        raise RuntimeError('attention block are only available '
                           'with the TensorFlow backend.')
    import tensorflow as tf

    def MultiHeadSelfAttention3D(
            Source,
            similarity="additive",
            kernel_initializer='glorot_uniform',
            wk_kernel_initializer='glorot_uniform'):
        if input_shape:
            S = Dense(
                num_units,
                activation=activation,
                input_shape=input_shape)(Source)
        else:
            S = Dense(
                num_units,
                activation=activation)(Source)
            length = S.shape[-2]
            step = length / 8
            S_ = [S[:, :, :]]