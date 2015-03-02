# Python APIs for Pivotal Tracker

pytracker is a simple Python API that wraps the [Pivotal Tracker][1] [REST APIs][2].

## This is a Fork

The original pytracker was developed by Doug Coker. [You can view the project here][3].

I've forked the project because it is no longer being maintained (the last commit was [Nov 30, 2010][4]). Furthermore, when this was originally developed it was intended for use with v2 of Pivotal Tracker's API which has been [disabled since January 27, 2012][5].

The goal of this project is to bring the library up-to-date with v5 of Pivtoal Tracker's API and utilize the existing methods.

Once the project is functioning as expected with v5, I'll look in to extending existing or creating new features.

## Contributing
Currently the goal is to convert everything from XML to JSON.
There are new endpoints to utilize in v5 and eventually the application will be extended to utilize them.
If you would like to contribute a new feature or bug fix:

1. Fork it
2. Create your feature branch (`git checkout -b my-new-feature`)
3. Commit your changes (`git commit -am 'Add some feature'`)
3. Push to the branch (`git push origin my-new-feature`)
4. Create a new Pull Request

## License
[Apache License 2.0][6]

[1]: http://www.pivotaltracker.com/
[2]: https://www.pivotaltracker.com/help/api
[3]: https://code.google.com/p/pytracker/
[4]: https://code.google.com/p/pytracker/source/detail?r=4c3c64281aca142fcac1803e856ee8ba771c68a3
[5]: http://www.pivotaltracker.com/community/tracker-blog/pivotal-tracker-api-v2-removal
[6]: http://www.apache.org/licenses/LICENSE-2.0
