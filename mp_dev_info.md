# OAuth

OAuth es un protocolo de autorización que permite que las aplicaciones tengan acceso limitado a la información privada de las cuentas de Mercado Pago. A través del protocolo HTTP, introduce una capa de autenticación y autorización, que consiste en solicitar acceso a los recursos protegidos de los vendedores mediante un **Access token** limitado a una aplicación en particular. Esto se logra sin necesidad de obtener las credenciales de los vendedores a través de los **flujos de acceso**.

> NOTE
>
> Nota
>
> El uso del protocolo OAuth difiere del proceso de uso compartido de credenciales. OAuth no aborda cuestiones relacionadas con la autenticación del cliente, ni información relacionada con la misma. Su responsabilidad radica en los métodos de obtención de un token para acceder a un recurso.
> <br><br>
> A la hora de utilizar OAuth, es importante tener en cuenta ciertos aspectos para que la integración funcione correctamente. Accede a las [Buenas prácticas de integración de OAuth](/developers/es/docs/security/oauth/best-practices) y consulta una guía de posibles errores y de buenas prácticas a tener en cuenta. 

## Access Token

És un código utilizado en diferentes _requests_ de origen público para acceder a un recurso protegido y representa una autorización otorgada por un vendedor a una aplicación cliente, que contiene _scopes_ y un tiempo de vigencia limitado para dicho acceso.

### Temporary grants

Los **_temporary grants_** son códigos temporales utilizados para ser intercambiados por un Access Token. A diferencia de los Access Token, sólo pueden ser usados para llamadas con el servidor de autorización y nunca se envían a servidores de recursos. Los tipos de _temporary grants_ son:

- `authorization_code`: tiene una duración de 10 minutos y su uso es único.
- `refresh_token`: tiene una duración de 6 meses y puede ser reutilizado.

Si deseas conocer cómo obtener el Access Token, accede a [nuestra documentación](/developers/es/guides/additional-content/security/oauth/creation). También puedes consultar la información necesaria para saber cómo [renovarlo](/developers/es/guides/additional-content/security/oauth/renewal).

## Flujos de acceso (grant types)

Los flujos, también llamados _grant types_, se refieren a la forma en que una aplicación obtiene un Access Token, credencial permite acceder a los datos expuestos a través de una API. En el caso de Mercado Pago, hay tres flujos de acceso disponibles:

- **Authorization code**: flujo basado en redirección y que debe ser usado si se van a usar credenciales para acceder a un recurso a nombre de un tercero. Está caracterizado por la intervención del usuario para autorizar explícitamente el acceso a sus datos por medio de la aplicación, y por el uso de un código proporcionado por el servidor de autenticación para que esta aplicación pueda obtener un Access Token y un `refresh_token` asociado. Puedes ver más información dirigiéndote a [Obtener Access Token](/developers/es/docs/security/oauth/creation#bookmark_authorization_code).
- **Refresh token**: en caso de que un Access Token generado a partir del flujo _Authorization code_ sea inválido o haya expirado, este flujo se utilizará para intercambiar una concesión temporal del tipo `refresh_token` por un Access Token. Es decir, permitirá que el Access Token se actualice sin una nueva interacción del usuario luego de haber concedido  la autorización por el flujo _Authorization code_. Puedes ver más información accediendo a [Renovar Access Token](/developers/es/guides/additional-content/security/oauth/renewal).
- **Client credentials**: se van a usar credenciales para acceder a un recurso en nombre propio, o sea, se utiliza para obtener un Access Token sin interacción del usuario. Es útil para instancias en que  las aplicaciones solicitan este Access Token usando solo sus propias credenciales para acceder a sus propios recursos, sin permitir actuar en nombre de un usuario ni acceder a sus datos. Puedes ver más información en la documentación [Obtener Access Token](/developers/es/docs/security/oauth/creation#bookmark_client_credentials).

> NOTE
>
> PKCE (Proof Key for Code Exchange)
>
> Si vas a utilizar el flujo **Authorization code** para obtener el Access Token, puedes configurar el **PKCE** (_Proof Key for Code Exchange_), un protocolo de seguridad utilizado con OAuth para proteger contra ataques de código malicioso durante el intercambio de códigos de autorización por Access Token. Añade una capa extra de seguridad generando un _verifier_ que se transforma en un _challenge_ para asegurar que, incluso si el código de autorización es interceptado, no sea útil sin el _verifier_ original.  Consulta [Configurar PKCE](/developers/es/docs/security/oauth/creation#:~:text=Access%20Token.-,Configurar%20PKCE,-El%20PKCE%20) para obtener más información.

# Obtener Access Token

Aprende a utilizar los flujos, también conocidos como _grant types_, para obtener un Access Token y acceder a los datos expuestos por una API. Estos flujos responden  a todos los escenarios de negocios que pueden aparecer en el consumo de APIs con base en el tipo de aplicación consumidora, su grado de confianza y cómo es la interacción del usuario en el proceso.

Los flujos de acceso disponibles para la generación del Access Token son:

- [Authorization code](/developers/es/docs/security/oauth/creation#bookmark_authorization_code): se van a usar credenciales para acceder a un recurso a nombre de un tercero.
- [Client credentials](/developers/es/docs/security/oauth/creation#bookmark_client_credentials): se van a usar credenciales para acceder a un recurso en nombre propio.

> WARNING
>
> Importante
>
> Si un Access Token generado a partir del flujo **Authorization code** es inválido o ha expirado, podrás utilizar el flujo **Refresh Token** para intercambiar una concesión temporal del tipo `refresh_token` por un Access Token. Esto  permite que el Access Token se actualice sin la necesidad de una nueva interacción del usuario después de la autorización concedida. Para más información, visita la documentación [Renovar Access Token](/developers/es/guides/additional-content/security/oauth/renewal).

## Authorization code

Este flujo se caracteriza por la intervención del vendedor para autorizar explícitamente el acceso de la aplicación a sus datos, y por el uso de un código otorgado por el servidor de autenticación para que la aplicación pueda obtener un Access Token y un _refresh token_ asociado.
Como se trata de un flujo basado en la redirección, debes permitir la interacción con el navegador del vendedor y recibir el `request` a través de la redirección del servidor de autorización. En este flujo, la aplicación solicita al vendedor el consentimiento expreso para acceder a los datos mediante la apertura de una página web, en la que se explicitan los ámbitos para los que se solicita el acceso.

> WARNING
>
> Importante
>
> Recuerda que utilizarás información sensible de tus vendedores. Asegúrate de guardarla de forma segura. No la utilices en la URL de autenticación y gestiona todo el proceso únicamente desde tu servidor.

Una vez autorizado, el servidor genera un código de acceso que llega a la aplicación a través de una redirección. En este paso, la aplicación solicita acceso al servidor de autenticación enviando el código obtenido y sus datos. Una vez hecho esto, el servidor otorga el Access Token y el _refresh token_ a la aplicación.

Mira a continuación cómo **configurar el protocolo PKCE** (un protocolo de seguridad no obligatorio que brinda una capa de protección extra, por lo que es recomendado) y luego **generar el Access Token**.

### Configurar PKCE

El **PKCE** (_Proof Key for Code Exchange_) es un protocolo de seguridad utilizado con OAuth para proteger contra ataques de código malicioso durante el intercambio de códigos de autorización por Access Token. Añade una capa adicional de seguridad generando un _verifier_ que se transforma en un _challenge_ para asegurar que, incluso si el código de autorización es interceptado, no sea útil sin el _verifier_ original.

Siga los pasos a continuación para habilitar y configurar el uso del flujo de código de autorización con PKCE.

1. Primero, en la pantalla de [Detalles de la aplicación](/developers/es/docs/your-integrations/application-details), haz clic en **Edita**r y **habilite el uso del flujo de código de autorización con PKCE**. Con el campo habilitado, Mercado Pago comenzará a **requerir como obligatorios** los campos `code_challenge` y `code_method` en las solicitudes de OAuth.
2. Los campos requeridos pueden generarse de varias formas, ya sea con desarrollo propio o mediante el uso de SDKs. Sigue los pasos necesarios descritos en [esta documentación oficial](https://datatracker.ietf.org/doc/html/rfc7636#section-4) para hacerlo.
3. Después de generar y cifrar los campos, será necesario enviar los códigos respectivos a Mercado Pago a través de `query_params`. Para eso, utiliza la URL de autenticación presentada a continuación, reemplazando los campos necesarios según se describen debajo.

```URL
https://auth.mercadopago.com/authorization?response_type=code&client_id=$APP_ID&redirect_uri=$YOUR_URL&code_challenge=$CODE_CHALLENGE&code_challenge_method=$CODE_METHOD
```

- **Redirect_uri**: URL proporcionada en el campo "URLs de redireccionamiento" de [tu aplicación](/developers/es/docs/your-integrations/application-details).
- **Code_verifier**: código que debe generarse, respetar los requisitos para su funcionamiento; es decir, ser una secuencia aleatoria de caracteres con una longitud de entre 43 y 128 caracteres, que incluya letras mayúsculas, minúsculas, números y algunos caracteres especiales. Por ejemplo: **47DEQpj8HBSa-_TImW-5JCeuQeRkm5NMpJWZG3hSuFU**.
- **Code_challenge**: a continuación, es necesario crear un `code_challenge`, a partir del `code_verifier`, utilizando una de las siguientes transformaciones:
 - Si es posible utilizar **S256**, será necesario seleccionar esta opción transformando el `code_verifier` en un `code_challenge` mediante una codificación `BASE64URL` después de aplicar la función "SHA256".
 - Si **no es posible utilizar S256** por alguna razón técnica, y el servidor admite el método **Plain**, es posible definir el `code_challenge` igual al `code_verifier`.
- **Code_challenge_method**: es el método utilizado para generar el `code_challenge`, según se describe en el ítem anterior. Este campo puede ser, por ejemplo, **S256** o **Plain**, dependiendo de la codificación seleccionada en la etapa de `code_challenge`. <br><br>

4. Después de enviar correctamente los códigos a Mercado Pago, obtendrás la autorización necesaria (`code_verifier`) para obtener el Access Token y realizar la verificación por PKCE en las transacciones realizadas con OAuth.

### Obtener token

El Access Token es el código utilizado en diferentes solicitudes de origen público para acceder a un recurso protegido. En este flujo, representa una autorización otorgada por un vendedor a una aplicación cliente, que contiene scopes y un tiempo de vigencia limitado para dicho acceso, y se concede por medio de una URL de redirección 

Sigue los pasos a continuación para obtenerlo.

> WARNING
>
> Atención
>
> Se recomienda realizar este procedimiento de una única vez junto con el usuario, ya que el código recibido por la "URL de redireccionamiento" después de la autorización tiene una validez de 10 minutos y el Access Token recibido a través del endpoint tiene una validez de 180 días (6 meses).

1. Edita tu aplicación para que contenga tu URLs de redireccionamiento. Consulta [Editar aplicación](/developers/es/docs/your-integrations/application-details).
2. Envía la **URL de autenticación** con los siguientes campos al vendedor con cuya cuenta deseas vincular la tuya:

   ```Authentication_URL
   https://auth.mercadopago.com/authorization?client_id=APP_ID&response_type=code&platform_id=mp&state=RANDOM_ID&redirect_uri=   https://www.mercadopago.com.br/developers/example/redirect-url 
   ```

   |Campos|Descripción|
   |---|---|
   |Client_id| Reemplaza el valor "APP_ID" con el **número de su aplicación**. Consulta [Detalles de la aplicación](/developers/es/docs/your-integrations/application-details) para más información.|
   |State| Reemplaza el valor "RANDOM_ID" con un identificador que sea único para cada intento y que no incluya información sensible, de forma que pueda identificar de quién es el código recibido. Así, podrás garantizar que la respuesta pertenezca a una solicitud iniciada por la misma aplicación. |
   |Redirect_uri| Agrega la URL informada en el campo "URLs de redireccionamiento" de su aplicación. **Asegúrate de que el redirect_uri sea una URL estática**. Consulta [Detalles de la aplicación](/developers/es/docs/your-integrations/application-details) para más información.|

   > Si deseas enviar parámetros adicionales en `redirect_uri`, utiliza el parámetro `state` para incluir esa información. De lo contrario, la llamada recibirá una respuesta de error si la URL no coincide exactamente con la configuración de la aplicación.

3. Espera a que el vendedor acceda a la URL y permita el acceso. Al ingresar a la URL, el vendedor será dirigido a Mercado Pago y deberá iniciar sesión en su cuenta para realizar la autorización.
4. Verifica la **URL de redireccionamiento** de tu servidor para ver el código de autorización devuelto en el parámetro de **code**.

   ```Redirect_URL
   https://www.mercadopago.com.br/developers/example/redirect-url 
   ```
  
5. Envía tus [credenciales](/developers/es/docs/your-integrations/credentials) (`client_id` y `client_secret`), el **código de autorización** que fue devuelto en la propiedad `code` y, si has [configurado el PKCE](/developers/pt/docs/security/oauth/creation#:~:text=Access%20Token.-,Configurar%20PKCE,-O%20PKCE%20), el valor `code_verifier` al endpoint [/oauth/token](/developers/es/reference/oauth/_oauth_token/post) para recibir el Access Token como respuesta.

[[[
```php
<?php
  $client = new OauthClient();
   $request = new OAuthCreateRequest();
     $request->client_secret = "CLIENT_SECRET";
     $request->client_id = "CLIENT_ID";
     $request->code = "CODE";
     $request->redirect_uri = "REDIRECT_URI";

  $client->create($request);
?>
```
```java

OauthClient client = new OauthClient();

String authorizationCode = "TG-XXXXXXXX-241983636";
client.createCredential(authorizationCode, null);
```
```node
const client = new MercadoPagoConfig({ accessToken: 'access_token', options: { timeout: 5000 } }); 

const oauth = new OAuth(client);

oauth.create({
	'client_secret': 'your-client-secret',
	'client_id': 'your-client-id',
	'code': 'return-of-getAuthorizationURL-function',
	'redirect_uri': 'redirect-uri'
}).then((result) => console.log(result))
	.catch((error) => console.log(error));
```
```curl
curl -X POST \
    'https://api.mercadopago.com/oauth/token'\
    -H 'Content-Type: application/json' \
    -d '{
  "client_id": "client_id",
  "client_secret": "client_secret",
  "code": "TG-XXXXXXXX-241983636",
  "grant_type": "authorization_code",
  "redirect_uri": "   https://www.mercadopago.com.br/developers/example/redirect-url ",
  "refresh_token": "TG-XXXXXXXX-241983636",
  "test_token": "false"
}'
```
]]]

> Para generar credenciales de _sandbox_ para pruebas, envía el parámetro `test_token` con el valor `true`.

## Client credentials

Este flujo se utiliza cuando las aplicaciones solicitan un Access Token usando solo sus propias credenciales y para acceder a sus propios recursos. La principal diferencia con respecto a los otros flujos es que el usuario no interactúa en el proceso y, por lo tanto, la aplicación no puede actuar en su nombre.

### Obtener token

Access Token es el código utilizado en diferentes solicitudes de origen público para acceder a un recurso protegido. En este flujo, se obtiene el Access Token sin interacción del usuario y solo para acceder a sus propios recursos.

Sigue los pasos a continuación para obtenerlo.

1. Envía tus [credenciales](/developers/es/docs/your-integrations/credentials) (`client_id` y `client_secret`) al endpoint [/oauth/token](/developers/es/reference/oauth/_oauth_token/post), incluyendo el código `client_credentials` en el parámetro `grant_type` para recibir una nueva respuesta con un nuevo `access_token`.
2. Actualiza la aplicación con el Access Token recibido en la respuesta. 

> WARNING
>
> Atención
>
> **El _token_ recibido tiene una validez de 6 horas.** No olvides renovarlo antes de este período de expiración para que sus aplicaciones sigan funcionando correctamente.

[[[
```php
<?php
  $client = new OauthClient();
   $request = new OAuthCreateRequest();
     $request->client_secret = "CLIENT_SECRET";
     $request->client_id = "CLIENT_ID";

  $client->create($request);
?>
```
```node
const client = new MercadoPagoConfig({ accessToken: 'access_token', options: { timeout: 5000 } }); 

const oauth = new OAuth(client);

oauth.create({
	'client_secret': 'your-client-secret',
	'client_id': 'your-client-id',
}).then((result) => console.log(result))
	.catch((error) => console.log(error));
```
```curl
curl -X POST \
    'https://api.mercadopago.com/oauth/token'\
    -H 'Content-Type: application/json' \
    -d '{
  "client_id": "client_id",
  "client_secret": "client_secret",
  "grant_type": "client_credentials",
}'
```
]]]

# Renovar Access Token
 
El flujo **Refresh token** se usa para intercambiar un **temporary grants** de tipo `refresh_token` por un Access Token cuando el que está en uso ha sido obtenido a través del flujo [Authorization code](/developers/es/docs/security/oauth/creation#bookmark_authorization_code) y **se encuentra próximo a caducar** y . El Access Token recibido a través de este llamado es **válido durante 180 días** (6 meses), luego de lo cual se debe reconfigurar todo el flujo de autorización.

Además, este flujo permite continuar utilizando un Access Token válido con las mismas características que el token original, sin necesidad de una nueva interacción con el usuario. Al implementarlo, el token original se intercambia por uno nuevo, que también ofrece la posibilidad de limitar los alcances al devolver un nuevo refresh token para intercambiarlo en el futuro.

> WARNING
>
> Importante
>
> Solo es posible utilizar este flujo si la aplicación retornar el parámetro `scope` indicando el valor `offline_access` y el vendedor ha autorizado previamente esta acción a partir del flujo de [Authorization code](/developers/es/docs/security/oauth/creation#bookmark_authorization_code).

Sigue los pasos a continuación para renovar el **Access Token**.

1. Envía el código de `refresh_token`, tus [credenciales](/developers/es/docs/your-integrations/credentials) y el `authorization_code` obtenido mediante el flujo de [Creación](/developers/es/docs/security/oauth/creation#bookmark_authorization_code) al endpoint [/oauth/token](/developers/es/reference/oauth/_oauth_token/post), incluyendo el código de `refresh_token` en el string `grant_type`, para recibir una nueva respuesta con un nuevo `access_token` y un nuevo `refresh_token`.
2. Actualiza la aplicación con el Access Token recibido en la respuesta.

> WARNING
>
> Importante
>
> Recuerda que cada vez que renueves el `access_token`, también se renovará el `refresh_token`, por lo que deberás almacenarlo nuevamente.

[[[
```php
<?php
  $client = new OauthClient();
  $request = new OAuthRefreshRequest();
    $request->client_secret = "CLIENT_SECRET";
    $request->client_id = "CLIENT_ID";
    $request->refresh_token = "REFRESH_TOKEN";

  $client->refresh($request);
?>
```
```java

OauthClient client = new OauthClient();

String refreshtoken = "TG-XXXXXXXX-241983636";
client.createCredential(refreshtoken, null);
```
```node
const client = new MercadoPagoConfig({ accessToken: 'access_token', options: { timeout: 5000 } });

const oauth = new OAuth(client);

oauth.refresh({
	'client_secret': 'your-client-secret',
	'client_id': 'your-client-id',
	'refresh_token': 'refresh-token'
}).then((result) => console.log(result))
	.catch((error) => console.log(error));
```
```curl
curl -X POST \
'https://api.mercadopago.com/oauth/token'\
-H 'Content-Type: application/json' \
-d '{
 "client_id": "client_id",
 "client_secret": "client_secret",
 "grant_type": "refresh_token",
 "refresh_token": "TG-XXXXXXXX-241983636"
}'
```
]]]
# Gestionar Access Token
 
Actualmente existen diferentes formas en las que un **_Access token_** y sus **_temporary grants_** creados se pueden deshabilitar e invalidar para autorizar solicitudes de recursos protegidos o para cambiarlos por nuevos tokens.

A continuación, tienes una lista detallada sobre cada una de estas maneras en las que estos permisos pueden ser deshabilitados.

* **Expiración**: después del tiempo establecido en el momento de la creación, el token caduca automáticamente y no se puede obtener.
* **Cambio de contraseña de usuario**: existen flujos de cambio de contraseña en los que el vendedor puede revocar todas tus credenciales, incluidos los tokens asociados y las _temporary grants_.
* **Revocación de la autorización**: revocar una autorización entre el vendedor y la aplicación desencadena la eliminación de todos los tokens y _temporary grants_ asociados a ellos.
* **Lavado de credenciales por fraude**: es posible que el departamento de Seguridad de la Información y Prevención de Fraudes realice una actualización completa de las credenciales de un usuario. Esto desencadena la eliminación de todos los tokens y _temporary grants_ asociados al vendedor en cuestión.
* **Limpieza de sesión de usuario**: activa la actualización de todos los tokens de vendedores y _temporary grants_.
* **Eliminación de la aplicación**: cuando se elimina una aplicación, se eliminan todos los tokens y _temporary grants_ que le pertenecen.

Puedes recibir notificaciones Webhooks cada vez que un vendedor autorice o desautorice tu aplicación. Para configurarlas, consulta la documentación de [Webhooks](/developers/es/docs/checkout-pro/additional-content/your-integrations/notifications/webhooks).

# Buenas prácticas de integración de OAuth

A la hora de utilizar OAuth, es importante tener en cuenta ciertos aspectos para que la integración funcione correctamente.

A continuación, encontrarás una guía de posibles errores y de buenas prácticas a tener en cuenta. 

## Uso correcto de los valores en los header de la solicitud 

Utiliza siempre los header `accept` y `content-type` en tu solicitud POST. Ten cuidado de no agregar valores a los headers que no sean parte de la integración para evitar recibir un error como respuesta.

![oauth_header](/images/oauth/oauth_header.png)

## Uso correcto de los valores 'params'

En tu llamada POST, ten cuidado de utilizar sólo los valores `params` solicitados. No agregues otros valores no requeridos ya que, de hacerlo, recibirás un código de error como respuesta.

![oauth_params](/images/oauth/oauth-1.png)

## Uso correcto de los Query Params

Recuerda no enviar ningún parámetro dentro de Query Params. Envía los parámetros dentro del cuerpo de la solicitud tal como se indica en [Referencia de API](/developers/es/reference/oauth/_oauth_token/post).

![oauth_queryparams](/images/oauth/oauth_queryparams_v2.png)

## Uso correcto del campo 'grant_type'

Utiliza siempre el campo `grant_type` en tus solicitudes con los valores `authorization_code` o `client_credentials`. Recuerda que si envias otro valor, es posible que recibas un error como respuesta.

![oauth_grant_type](/images/oauth/oauth_granttype_v2.png)

## Uso del campo 'state' en la solicitud del 'autorization code'

Para aumentar la seguridad de la integración, recomendamos incluir el parámetro `state` en el flujo de solicitud del `authorization code`. Así, podrás garantizar que la respuesta pertenezca a una solicitud iniciada por la misma aplicación. 

**Asegúrate de que el `redirect_uri` sea una URL estática**. Si deseas enviar parámetros adicionales en esa URL, utiliza el parámetro `state` para incluir esa información. De lo contrario, la llamada recibirá una respuesta de error si el `redirect_uri` no coincide exactamente con la configuración de la aplicación.

![oauth_state](/images/oauth/oauth_state_v4.png)

Para encontrar más información acerca de la solicitud, sus parámetros y las posibles respuestas de éxito y error que puedes recibir, ve a la documentación de [Referencia de API](/developers/es/reference/oauth/_oauth_token/post).