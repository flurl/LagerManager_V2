## Morandell

Please extract the following information from this document(s):

- Date of delivery
- Invoice Number
- the delivered articles (ID, Name, quantity, total_price, discount, beer_tax, tax)
- the total sum net and gross

The quantity has to be calculated by multiplying the "Inhalt" column with the "Menge" column. For example 1,0L/6   5 KK means there were a total of 6*5=30 1L bottles delivered. Only if the unit of the "Menge" is FL there's no need for a calculatzion, because FL means Flasche

The total price is the amount in the "Betrag" column,. The discount is also given in the betrag column, but with a negative sign appended. The beer tax/Biersteuer is also listed in the Betrag column.
The returned JSON should look like this:
{
"date_of_delivery": "2026-02-27",
invoice_number: "INVOICE_NUMBER
"total_sum_net": 2125.45,
"total_sum_gross": 2550.54,
"articles": [
{
"ID": ARTICLE_ID,
"Name": "ARTICLE_NAME",
"quantity": QUANTITY,
"total_price": TOTAL_PRICE,
"discount": DISCOUNT,
"beer_tax": BEER_TAX,
"tax": TAX
},
...
}

Some notes for the article mapping:
Grasovska = Bueffelgraswodka
Steirerquell = Mineralwasser

Do not distinguish Schweppes by flavor, only by bottle size. 

To get the article ID please map the article name to an ID - best effort - using the following lookup table. If you can't identify an article use null as article ID

%%article_table%%

## Transgourmet

Please extract the following information from this document(s):

- Date of delivery
- Invoice Number
- the delivered articles (ID, Name, quantity, total_price, discount, beer_tax, tax)
- the total sum net and gross

The quantity is given in the column Liefermenge. It might be specified by two quantities. For example 10 KT 240 FL means 10 packages with each having 24 bottles totaling to 240 bottles.
The Artikelbezeichnung column is the aticle name.
The Stückpreis column has the price per unit and the Warenbetrag is the total price for each article. We need the total price for each article, you can ignore the Stückpreis column.

Watch out for any discount or beer taxes.


The returned JSON should look like this:
{
"date_of_delivery": "2026-02-27",
invoice_number: "INVOICE_NUMBER
"total_sum_net": 2125.45,
"total_sum_gross": 2550.54,
"articles": [
{
"ID": ARTICLE_ID,
"Name": "ARTICLE_NAME",
"quantity": QUANTITY,
"total_price": TOTAL_PRICE,
"discount": DISCOUNT,
"beer_tax": BEER_TAX,
"tax": TAX
},
...
}

Some notes for the article mapping:
Grasovska = Bueffelgraswodka
Steirerquell = Mineralwasser
Eule Bier EW 0,33L = Eule 0,33L

Do not distinguish Schweppes by flavor, only by bottle size. 

To get the article ID please map the article name to an ID - best effort - using the following lookup table. If you can't identify an article use null as article ID

%%article_table%%

## Murauer:

Please extract the following information from this document(s):

- Date of delivery
- Invoice Number
- the delivered articles (ID, Name, quantity, total_price, discount, beer_tax, tax)
- the total sum net and gross

The quantity is given by a combination of the Menge column and the Bezeichnung. In the Bezeichnung there is the number of units per package encoded. It's the nunber after the forward slash after the article name. For example: 0,33l/24 means there are 24 bottles with a volume of 0,33 litres in on package. That number has to be multiplied by the number of packages from the Menge column to get the total quantity for an article.
The Bezeichnung column is the article name with the quantity encoding.
The "Gesamtpreis Rabatt" column contains the total price and a possible discount.
The "Betrag" column contains the Gesamtpreis minus Rabatt and a possible beer tax (Biersteuer).
The Gesamtpreis should be mapped to the total_price key, the rabatt to the discount key and the Biersteuer to the beer_tax key. 


The returned JSON should look like this:
{
"date_of_delivery": "2026-02-27",
invoice_number: "INVOICE_NUMBER
"total_sum_net": 2125.45,
"total_sum_gross": 2550.54,
"articles": [
{
"ID": ARTICLE_ID,
"Name": "ARTICLE_NAME",
"quantity": QUANTITY,
"total_price": TOTAL_PRICE,
"discount": DISCOUNT,
"beer_tax": BEER_TAX,
"tax": TAX
},
...
}


To get the article ID please map the article name to an ID - best effort - using the following lookup table. If you can't identify an article use null as article ID

%%article_table%%

## Engel

Please extract the following information from this document(s):

- Date of delivery
- Invoice Number
- the delivered articles (ID, Name, quantity, total_price, discount, beer_tax, tax)
- the total sum net and gross

The Menge column contains the quantity in bottles.
The Beschreibung column is the aticle name.
The Netto column contains the total price.
The Netto column should be mapped to the total_price key.

Watch out for any discounts.


The returned JSON should look like this:
{
"date_of_delivery": "2026-02-27",
invoice_number: "INVOICE_NUMBER
"total_sum_net": 2125.45,
"total_sum_gross": 2550.54,
"articles": [
{
"ID": ARTICLE_ID,
"Name": "ARTICLE_NAME",
"quantity": QUANTITY,
"total_price": TOTAL_PRICE,
"discount": DISCOUNT,
"beer_tax": BEER_TAX,
"tax": TAX
},
...
}

Some hints for the article mapping:
Landwein Liter Cuvee = Hauswein weiss 1L

To get the article ID please map the article name to an ID - best effort - using the following lookup table. If you can't identify an article use null as article ID

%%article_table%%

## Braununion

Please extract the following information from this document(s):

- Date of delivery
- Invoice Number
- the delivered articles (ID, Name, quantity, total_price, discount, beer_tax, tax)
- the total sum net and gross

The quantity is given by a combination of the Menge column and the Bezeichnung. In the Bezeichnung there is the number of units per package encoded. For example: 24x33cl means there are 24 bottles with a volume of 0,33 litres in on package. That number has to be multiplied by the number of packages from the Menge column to get the total quantity for an article.
The Bezeichnung column is the article name with the quantity encoding.
The "Gesamtpreis Rabatt" column contains the total price and a possible discount.
The "Betrag" column contains the Gesamtpreis minus Rabatt and a possible beer tax (Biersteuer).
The Gesamtpreis should be mapped to the total_price key, the rabatt to the discount key and the Biersteuer to the beer_tax key. 

Watch out for any discounts.


The returned JSON should look like this:
{
"date_of_delivery": "2026-02-27",
invoice_number: "INVOICE_NUMBER
"total_sum_net": 2125.45,
"total_sum_gross": 2550.54,
"articles": [
{
"ID": ARTICLE_ID,
"Name": "ARTICLE_NAME",
"quantity": QUANTITY,
"total_price": TOTAL_PRICE,
"discount": DISCOUNT,
"beer_tax": BEER_TAX,
"tax": TAX
},
...
}

Some hints for the article mapping:
Landwein Liter Cuvee = Hauswein weiss 1L

To get the article ID please map the article name to an ID - best effort - using the following lookup table. If you can't identify an article use null as article ID

%%article_table%%


